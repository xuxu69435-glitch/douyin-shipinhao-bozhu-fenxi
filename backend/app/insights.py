"""Strict LLM JSON contract and server-owned, immutable transcript evidence anchors."""

import json
import asyncio
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

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

    @field_validator("primary_domain", mode="before")
    @classmethod
    def unknown_domain(cls, value):
        # Insufficient evidence is a valid outcome, never invent a domain to fill a tag.
        return "未分类" if isinstance(value, str) and not value.strip() else value

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
primary_domain 必须是非空字符串，领域证据不足时统一填写“未分类”，不要猜测领域。
"""


class OpenAICompatibleInsightGenerator:
    """Makes a real OpenAI-compatible chat-completion request (no fake fallback)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        if not all(x and x.strip() for x in (base_url, api_key, model)):
            raise ValueError("需要完整配置 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL")
        if not base_url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise ValueError("OPENAI_BASE_URL必须使用HTTPS或本机HTTP")
        from .runtime_settings import RuntimeSettings
        self.base_url = RuntimeSettings(OPENAI_BASE_URL=base_url).OPENAI_BASE_URL
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.cache_identity = self.base_url + "|" + self.model
        self.last_run = {}

    MAX_REQUESTS = 12
    MAX_CHUNKS = 5
    CHUNK_CHARACTERS = 16_000
    MAX_OUTPUT_TOKENS = 4096

    async def generate(self, segments: list[Any]) -> dict[str, Any]:
        payload = [
            {"segment_id": seg.segment_id, "start_ms": seg.start_ms,
             "end_ms": seg.end_ms, "text": seg.text}
            for seg in segments
        ]
        self.last_run = {"harness_version": "fixed-analysis-v1", "requests": 0,
                         "max_requests": self.MAX_REQUESTS, "max_output_tokens": self.MAX_OUTPUT_TOKENS,
                         "prompt_tokens": 0, "completion_tokens": 0, "usage_reported": False, "chunks": 0}
        chunks = []
        current = []
        size = 2
        for segment in payload:
            encoded = json.dumps(segment, ensure_ascii=False, separators=(",", ":"))
            if len(encoded) > self.CHUNK_CHARACTERS:
                raise ValueError("单个字幕段超过分析上下文上限，请先检查字幕分段")
            if current and size + len(encoded) + 1 > self.CHUNK_CHARACTERS:
                chunks.append(current)
                current, size = [], 2
            current.append(segment)
            size += len(encoded) + 1
        if current:
            chunks.append(current)
        if not chunks or len(chunks) > self.MAX_CHUNKS:
            raise ValueError("字幕为空或超过本版的 5 个分段上限；已停止，避免无限请求")
        self.last_run["chunks"] = len(chunks)
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            results = []
            for chunk in chunks:
                results.append(await self._request(client, "字幕逐段数据：\n" + json.dumps(chunk, ensure_ascii=False),
                                                   {segment["segment_id"] for segment in chunk}))
            if len(results) == 1:
                return results[0]
            synthesis = json.dumps(results, ensure_ascii=False)
            if len(synthesis) > 48_000:
                raise ValueError("分段结果超过汇总上下文上限，已停止并保留原始字幕")
            return await self._request(client,
                "以下是按字幕生成且已校验引用的分段 JSON。请合并同义主题、去重观点，归纳整条视频。"
                "只使用已有分段结果，保留其字幕段 ID，不新增事实或身份认证。输出同一 JSON 格式：\n" + synthesis,
                {segment["segment_id"] for segment in payload})

    async def _request(self, client, content, allowed_ids):
        body = {"model": self.model, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"}, "max_tokens": self.MAX_OUTPUT_TOKENS}
        for attempt in range(2):
            if self.last_run["requests"] >= self.MAX_REQUESTS:
                raise ValueError("已达到单视频模型请求上限")
            self.last_run["requests"] += 1
            try:
                response = await client.post(self.base_url + "/chat/completions", json=body,
                                             headers={"Authorization": f"Bearer {self.api_key}"})
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage") or {}
                if usage:
                    self.last_run["usage_reported"] = True
                for field in ("prompt_tokens", "completion_tokens"):
                    value = usage.get(field, 0)
                    if isinstance(value, int) and value >= 0:
                        self.last_run[field] += value
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ValueError("模型输出达到 token 上限，未保存不完整结果")
                text = choice["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError("模型未返回 JSON 字符串")
                draft = InsightDraft.model_validate(json.loads(text))
                referenced = set(draft.summary_segment_ids)
                for statement in draft.key_claims + draft.explicitly_stated_preferences + draft.discussed_entities:
                    referenced.update(statement.segment_ids)
                if not referenced <= allowed_ids:
                    raise EvidenceIntegrityError("模型引用了当前材料中不存在的字幕段")
                return draft.model_dump()
            except httpx.HTTPStatusError as exc:
                if attempt or exc.response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise
            except (httpx.TransportError, ValueError, KeyError, IndexError, TypeError):
                if attempt:
                    raise
            await asyncio.sleep(0.5)
        raise RuntimeError("模型请求未能完成")
