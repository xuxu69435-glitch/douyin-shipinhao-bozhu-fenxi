"""Persistence-backed evidence inspection and subtitle export."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import TranscriptSegment, VideoAnalysis, VideoRecord


def segments_for_version(session: Session, video_id: str, transcript_version: str):
    return list(session.scalars(select(TranscriptSegment).where(
        TranscriptSegment.video_id == video_id,
        TranscriptSegment.transcript_version == transcript_version,
    ).order_by(TranscriptSegment.segment_id)))


def milliseconds_to_srt(ms: int, vtt: bool = False) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, frac = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}{'.' if vtt else ','}{frac:03}"


def subtitles_text(segments: list[TranscriptSegment], fmt: str) -> str:
    if fmt not in {"srt", "vtt"}:
        raise ValueError("fmt must be srt or vtt")
    result = ["WEBVTT", ""] if fmt == "vtt" else []
    for i, item in enumerate(segments, 1):
        if fmt == "srt":
            result.append(str(i))
        result.append(f"{milliseconds_to_srt(item.start_ms, fmt == 'vtt')} --> {milliseconds_to_srt(item.end_ms, fmt == 'vtt')}")
        result.extend([item.text, ""])
    return "\n".join(result).rstrip() + "\n"


def assert_analysis_integrity(session: Session, analysis: VideoAnalysis) -> None:
    """Check persisted citations before export; storage also can be tampered."""
    indexed = {x.segment_id: x for x in segments_for_version(session, analysis.video_id, analysis.transcript_version)}
    result = analysis.result
    all_refs = list(result.get("summary_evidence", []))
    for key in ("key_claims", "explicitly_stated_preferences", "discussed_entities"):
        for statement in result.get(key, []):
            all_refs.extend(statement.get("evidence", []))
    for ref in all_refs:
        item = indexed.get(ref.get("segment_id"))
        if (item is None or ref.get("video_id") != analysis.video_id
                or ref.get("transcript_version") != analysis.transcript_version
                or ref.get("start_ms") != item.start_ms or ref.get("end_ms") != item.end_ms):
            raise ValueError("Persisted analysis has broken evidence references")


def assert_report_integrity(session: Session, result: dict) -> None:
    """Resolve every exported report anchor against immutable storage.

    Do not render a stale report as evidentiary when a transcript/version has
    been removed or a source URL was tampered with.
    """
    refs: list[dict] = []
    for name in ("main_directions", "topic_tendencies", "frequently_discussed_entities"):
        for item in result.get(name, []):
            refs.extend(item.get("evidence", []))
    for name in ("key_claims_with_evidence", "creator_preferences_verified",
                 "preferences_not_attributed_to_creator"):
        for item in result.get(name, []):
            refs.extend(item.get("evidence", []))
    for ref in refs:
        video_id = ref.get("video_id")
        transcript_version = ref.get("transcript_version")
        segment_id = ref.get("segment_id")
        if not isinstance(video_id, str) or not isinstance(transcript_version, str) or type(segment_id) is not int:
            raise ValueError("报告证据索引字段非法")
        video = session.get(VideoRecord, video_id)
        if video is None or video.source_url != ref.get("source_url") or video.platform_video_id != ref.get("platform_video_id"):
            raise ValueError("报告来源视频已不存在或来源信息发生变化")
        part = session.scalar(select(TranscriptSegment).where(
            TranscriptSegment.video_id == video_id,
            TranscriptSegment.transcript_version == transcript_version,
            TranscriptSegment.segment_id == segment_id,
        ))
        if part is None or part.start_ms != ref.get("start_ms") or part.end_ms != ref.get("end_ms"):
            raise ValueError("报告引用的字幕版本或时间戳已失效")
