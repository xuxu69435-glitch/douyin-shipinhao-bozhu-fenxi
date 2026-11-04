"""M2 deterministic creator-level statistics with provenance checked against DB.

The language model supplies only per-video labels and cited statements. The
program is responsible for ratios and never promotes a narrator to creator.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence import assert_analysis_integrity
from .models import CreatorReport, TaskRecord, TaskVideoRecord, VideoAnalysis, VideoRecord
from .pipeline import version_key


class ReportNotReady(RuntimeError):
    pass


DOMAIN_ALIASES = {
    "ai": "人工智能", "a.i.": "人工智能", "人工智能技术": "人工智能", "人工智能": "人工智能",
    "科技数码": "科技", "科学技术": "科技", "科技": "科技",
    "生活日常": "生活", "日常生活": "生活", "生活": "生活",
}
THEME_ALIASES = {
    "ai工具": "AI工具", "人工智能工具": "AI工具", "ai tools": "AI工具", "ai tool": "AI工具",
    "大模型": "大语言模型", "llm": "大语言模型", "大语言模型": "大语言模型",
    "旅游": "旅行", "旅行": "旅行", "出游": "旅行",
}


def canonical_label(label: str, aliases: dict[str, str]) -> str:
    normalized = unicodedata.normalize("NFKC", label).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return aliases.get(normalized.casefold(), normalized)


def evidence_with_video(ref: dict[str, Any], video: VideoRecord,
                        analysis_version: str) -> dict[str, Any]:
    """All refs are pre-validated against persisted segments."""
    return {**ref, "platform_video_id": video.platform_video_id,
            "source_url": video.source_url, "analysis_version": analysis_version}


def build_creator_report(session: Session, task_id: str) -> CreatorReport:
    task = session.get(TaskRecord, task_id)
    if not task:
        raise ReportNotReady("任务不存在")
    linked = list(session.execute(select(VideoRecord, TaskVideoRecord).join(
        TaskVideoRecord, TaskVideoRecord.video_id == VideoRecord.id,
    ).where(TaskVideoRecord.task_id == task_id)).all())
    if not linked:
        raise ReportNotReady("尚未采集或关联任何作品，不能生成博主报告")

    creator_ids = {video.author_platform_id for video, _ in linked}
    if len(creator_ids) != 1:
        raise ReportNotReady("同一任务内出现不同作者ID，停止归纳")
    creator_id = next(iter(creator_ids))
    if task.source_kind == "profile" and task.platform_id and task.platform_id != creator_id:
        raise ReportNotReady("任务主页作者ID与作品实际作者不一致")

    latest: list[tuple[VideoRecord, VideoAnalysis]] = []
    for video, assoc in linked:
        if assoc.status in {"failed", "no_speech", "cancelled"}:
            continue
        row = session.scalar(select(VideoAnalysis).where(
            VideoAnalysis.video_id == video.id
        ).order_by(VideoAnalysis.created_at.desc(), VideoAnalysis.analysis_version.desc()))
        if row is None:
            continue
        assert_analysis_integrity(session, row)
        latest.append((video, row))
    if not latest:
        raise ReportNotReady("没有可用且通过证据校验的单视频分析结果")

    provenance_set = {analysis.result.get("provenance") for _, analysis in latest}
    if len(provenance_set) != 1 or provenance_set - {"real_model", "test_fixture"}:
        raise ReportNotReady("不同或未知来源的分析结果不能混合到同一报告")
    provenance = next(iter(provenance_set))
    evidence_versions = [f"{v.id}:{a.analysis_version}:{a.transcript_version}" for v, a in latest]
    evidence_version = version_key("evidence", *sorted(evidence_versions))
    task_stage_signature = json.dumps([(v.platform_video_id, assoc.status, assoc.error_code) for v, assoc in linked], ensure_ascii=False)
    report_version = version_key("report", task_id, evidence_version, "report-m2-v1", str(task.max_videos), task.stop_reason or "", task_stage_signature)
    cached = session.scalar(select(CreatorReport).where(
        CreatorReport.task_id == task_id, CreatorReport.report_version == report_version,
    ))
    if cached:
        return cached

    counts: dict[str, Counter[str]] = {"domain": Counter(), "theme": Counter(), "entity": Counter()}
    supports: dict[str, dict[str, list[dict[str, Any]]]] = {
        "domain": defaultdict(list), "theme": defaultdict(list), "entity": defaultdict(list),
    }
    statements = []
    verified_creator_preferences = []
    uncertain_preferences = []

    for video, analysis in latest:
        result = analysis.result
        refs = [evidence_with_video(ref, video, analysis.analysis_version)
                for ref in result["summary_evidence"]]
        domain = canonical_label(result["primary_domain"], DOMAIN_ALIASES)
        if domain:
            counts["domain"][domain] += 1
            supports["domain"][domain].extend(refs[:3])
        for name in sorted({canonical_label(x, THEME_ALIASES) for x in result.get("secondary_topics", [])}):
            if name:
                counts["theme"][name] += 1
                supports["theme"][name].extend(refs[:3])
        per_video_entities = set()
        for entity in result.get("discussed_entities", []):
            name = canonical_label(entity["text"], {})
            if not name or name in per_video_entities:
                continue
            per_video_entities.add(name)
            counts["entity"][name] += 1
            supports["entity"][name].extend([
                evidence_with_video(ref, video, analysis.analysis_version)
                for ref in entity["evidence"]
            ])
        for kind in ("key_claims", "explicitly_stated_preferences"):
            for value in result.get(kind, []):
                obj = {
                    "text": value["text"], "speaker_role": value["speaker_role"],
                    "attribution_basis": value["attribution_basis"],
                    "creator_identity_verified": bool(value.get("creator_identity_verified", False)),
                    "source_video_id": video.id,
                    "evidence": [evidence_with_video(ref, video, analysis.analysis_version)
                                 for ref in value["evidence"]],
                }
                if kind == "key_claims":
                    statements.append(obj)
                elif obj["speaker_role"] == "creator" and obj["creator_identity_verified"]:
                    verified_creator_preferences.append(obj)
                else:
                    uncertain_preferences.append(obj)

    total = len(latest)

    def percentage_rows(key: str):
        return [{"name": name, "count": count, "percentage": round(100 * count / total, 2),
                 "evidence": supports[key][name][:12]}
                for name, count in sorted(counts[key].items(), key=lambda x: (-x[1], x[0]))]

    failed = [{"platform_video_id": video.platform_video_id,
               "code": assoc.error_code or assoc.status,
               "message": assoc.error_message or ""}
              for video, assoc in linked if assoc.status in {"failed", "cancelled"}]
    no_speech = [video.platform_video_id for video, assoc in linked if assoc.status == "no_speech"]
    domains = percentage_rows("domain")
    themes = percentage_rows("theme")
    result = {
        "schema_version": "report-m2-v1", "provenance": provenance,
        "task_id": task_id, "creator_platform_id": creator_id,
        "sample": {
            "requested_limit": task.max_videos,
            "collected_count": len(linked), "analyzed_count": total,
            "failed_count": len(failed), "no_speech_count": len(no_speech),
            "unanalysed_count": len(linked) - total - len(failed) - len(no_speech),
            "stop_reason": task.stop_reason, "failed_videos": failed,
            "no_speech_platform_ids": no_speech,
        },
        "main_directions": domains,
        "topic_tendencies": themes,
        "frequently_discussed_entities": percentage_rows("entity"),
        "key_claims_with_evidence": statements,
        "creator_preferences_verified": verified_creator_preferences,
        "preferences_not_attributed_to_creator": uncertain_preferences,
        "business_claim": None,  # M2 cannot infer someone's business from general topic labels.
        "summary": (
            f"基于{total}条有效视频，主要内容方向："
            + ("、".join(f"{x['name']}({x['percentage']}%)" for x in domains[:3]) if domains else "暂无明确分类")
            + "。主要选题："
            + ("、".join(f"{x['name']}({x['percentage']}%)" for x in themes[:4]) if themes else "暂无明确主题")
            + "。此结果仅描述抽样视频内容，不代表对博主身份或个人喜好的认证。"
        ),
        "evidence_versions": sorted(evidence_versions),
    }
    report = CreatorReport(task_id=task_id, report_version=report_version,
                           evidence_version=evidence_version, result=result)
    session.add(report)
    session.flush()
    return report


def export_report_markdown(result: dict[str, Any]) -> str:
    sample = result["sample"]
    out = [
        "# 博主公开内容分析报告", "",
        f"来源性质：{result['provenance']}（test_fixture仅用于测试，不代表真实模型结果）", "",
        f"作者平台ID：`{result['creator_platform_id']}`", "",
        f"分析范围：要求最多{sample['requested_limit']}条；实际关联{sample['collected_count']}条；有效{sample['analyzed_count']}条；失败{sample['failed_count']}条；无有效语音{sample['no_speech_count']}条。", "",
        f"停止原因：{sample['stop_reason'] or '未记录'}", "",
        "## 概览", "", result["summary"], "",
    ]
    for title, key in (("主要领域", "main_directions"), ("选题倾向", "topic_tendencies"),
                       ("高频讨论对象", "frequently_discussed_entities")):
        out += [f"## {title}", ""]
        if not result[key]:
            out += ["暂无可证实的统计结果。", ""]
        for item in result[key]:
            out += [f"- {item['name']}：{item['count']}条（{item['percentage']}%）"]
            for ref in item["evidence"][:3]:
                out += [f"  - 证据：[原作品]({ref['source_url']}) · {ref['start_ms']}–{ref['end_ms']}毫秒 · 字幕段{ref['segment_id']} · 转写版本`{ref['transcript_version']}`"]
        out.append("")
    out += ["## 主体归属与偏好", ""]
    if result["creator_preferences_verified"]:
        for item in result["creator_preferences_verified"]:
            out.append(f"- {item['text']}（已核实归属；证据段：{item['evidence'][0]['segment_id']}）")
    else:
        out.append("无经过独立身份核实的博主本人偏好；视频叙述者和引用对象的表达不归因于博主。")
    if result["preferences_not_attributed_to_creator"]:
        out += ["", "### 视频中出现但未归属于博主的偏好表达", ""]
        for item in result["preferences_not_attributed_to_creator"]:
            ref = item["evidence"][0]
            out.append(f"- [{item['speaker_role']}] {item['text']} · [来源]({ref['source_url']}) · 字幕段{ref['segment_id']}")
    out += ["", "## 主要业务归纳", "", "公开证据不足，暂不推断主营业务。", ""]
    if sample["failed_videos"]:
        out += ["## 失败作品", ""]
        for item in sample["failed_videos"]:
            out += [f"- `{item['platform_video_id']}`：{item['code']} — {item['message']}"]
        out.append("")
    return "\n".join(out)
