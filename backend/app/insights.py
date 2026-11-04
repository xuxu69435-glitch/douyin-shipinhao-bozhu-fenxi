"""Strict LLM JSON contract and server-owned, immutable transcript evidence anchors."""

import json
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import EvidenceRef

SpeakerRole = Literal["creator", "narrator", "guest", "quoted", "unknown"]


class EvidenceStatementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    speaker_role: SpeakerRole
    attribution_basis: str = Field(min_length=1, max_length=800)
    segment_ids: list[int] = Field(min_length=1, max_length=12)


class InsightDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=3000)
    summary_segment_ids: list[int] = Field(min_length=1, max_length=20)
    primary_domain: str = Field(min_length=1, max_length=120)
    secondary_topics: list[str] = Field(max_length=12)
    content_format: str = Field(min_length=1, max_length=120)
    key_claims: list[EvidenceStatementDraft] = Field(max_length=20)
    explicitly_stated_preferences: list[EvidenceStatementDraft] = Field(max_length=20)
    discussed_entities: list[EvidenceStatementDraft] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nonblank_tags(self):
        if any(not x.strip() for x in self.secondary_topics):
            raise ValueError("secondary_topics contains blank entries")
        return self


class AnchoredStatement(BaseModel):
    text: str
    speaker_role: SpeakerRole
    attribution_basis: str
    creator_identity_verified: bool = False
    evidence: list[EvidenceRef]


class AnchoredInsight(BaseModel):
    summary: str
    summary_evidence: list[EvidenceRef]
    primary_domain: str
    secondary_topics: list[str]
    content_format: str
    key_claims: list[AnchoredStatement]
    explicitly_stated_preferences: list[AnchoredStatement]
    discussed_entities: list[AnchoredStatement] = Field(default_factory=list)
    provenance: Literal["real_model", "test_fixture"] = "real_model"


class EvidenceIntegrityError(ValueError):
    pass


def anchor_insight(
    raw: dict[str, Any], video_id: str, transcript_version: str,
    segments: list[Any], provenance: Literal["real_model", "test_fixture"] = "real_model",
) -> AnchoredInsight:
    """LLM may specify segment IDs, but NEVER video IDs, versions or timestamps.

    The caller supplies stored segment records. Every claimed ID is verified
    against that exact video+transcript version before persisting any insight.
    The output never automatically verifies that the uploader is the narrator.
    """
    draft = InsightDraft.model_validate(raw)
    by_id = {}
    for segment in segments:
        if segment.video_id != video_id or segment.transcript_version != transcript_version:
            raise EvidenceIntegrityError("Mixed transcript/video versions in input")
        by_id[segment.segment_id] = segment
    if not by_id:
        raise EvidenceIntegrityError("No transcript segments exist")

    def anchors(ids: list[int]) -> list[EvidenceRef]:
        if len(set(ids)) != len(ids):
            raise EvidenceIntegrityError("Duplicate evidence segment IDs")
        if any(type(i) is not int or i not in by_id for i in ids):
            raise EvidenceIntegrityError("LLM cited a nonexistent segment ID")
        return [EvidenceRef(
            video_id=video_id, transcript_version=transcript_version,
            segment_id=i, start_ms=by_id[i].start_ms, end_ms=by_id[i].end_ms,
        ) for i in ids]

    def statement(item: EvidenceStatementDraft) -> AnchoredStatement:
        return AnchoredStatement(
            text=item.text, speaker_role=item.speaker_role,
            attribution_basis=item.attribution_basis,
            creator_identity_verified=False, evidence=anchors(item.segment_ids),
        )

    return AnchoredInsight(
        summary=draft.summary, summary_evidence=anchors(draft.summary_segment_ids),
        primary_domain=draft.primary_domain.strip(),
        secondary_topics=list(dict.fromkeys(x.strip() for x in draft.secondary_topics)),
        content_format=draft.content_format.strip(),
        key_claims=[statement(item) for item in draft.key_claims],
        explicitly_stated_preferences=[statement(item) for item in draft.explicitly_stated_preferences],
        discussed_entities=[statement(item) for item in draft.discussed_entities],
        provenance=provenance,
    )


class InsightGenerator(Protocol):
    async def generate(self, segments: list[Any]) -> dict[str, Any]: ...


SYSTEM_PROMPT = """你是短视频内容证据分析器。只使用提供的带segment_id的原始字幕回答。
返回一个纯JSON对象，字段严格如下：
summary:string, summary_segment_ids:int[], primary_domain:string,
secondary_topics:string[], content_format:string,
key_claims:[{text:string,speaker_role:string,attribution_basis:string,segment_ids:int[]}],
explicitly_stated_preferences:[{text:string,speaker_role:string,attribution_basis:string,segment_ids:int[]}],
discussed_entities:[{text:string,speaker_role:string,attribution_basis:string,segment_ids:int[]}].
speaker_role只能是creator,narrator,guest,quoted,unknown之一；身份未知请用unknown或narrator。
只摘取有明确字幕证据的观点与偏好，不能把旁白、嘉宾、引用者的表述直接当成博主喜好。
每条陈述都必须有真实segment_id。discussed_entities只列出明确讨论的人物/品牌/产品等对象，不能推断没有出现的对象。不要填写video_id、时间戳、来源网址等字段。
无法确定的内容宁可不填写；主营业务仅凭字幕无法证实则不要断言。
"""


class OpenAICompatibleInsightGenerator:
    """Makes a real OpenAI-compatible chat-completion request (no fake fallback)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        if not all(x and x.strip() for x in (base_url, api_key, model)):
            raise ValueError("需要完整配置 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL")
        if not base_url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise ValueError("OPENAI_BASE_URL必须使用HTTPS或本机HTTP")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def generate(self, segments: list[Any]) -> dict[str, Any]:
        payload = [
            {"segment_id": seg.segment_id, "start_ms": seg.start_ms,
             "end_ms": seg.end_ms, "text": seg.text}
            for seg in segments
        ]
        transcript_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(transcript_json) > 48_000:
            raise ValueError("字幕超过M1单次模型请求长度，请分段处理而不是截断证据")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"字幕逐段数据：\n{transcript_json}"},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15)) as client:
            response = await client.post(
                self.base_url + "/chat/completions", json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("模型未返回JSON字符串")
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("模型结果不是JSON对象")
        return result
