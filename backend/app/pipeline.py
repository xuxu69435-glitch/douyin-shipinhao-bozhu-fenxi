"""M1: one real media -> verified file -> ASR -> validated LLM -> immutable evidence.

Collector and UI are deliberately separate. Tests inject deterministic fakes and
label those rows as fixtures; the normal path requires actual model calls.
"""

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .insights import InsightGenerator, anchor_insight
from .media import extract_audio, probe_media
from .models import TranscriptSegment, VideoAnalysis, VideoRecord
from .transcription import Transcriber


@dataclass(frozen=True)
class ProcessingOutcome:
    video_id: str
    status: Literal["analyzed", "no_speech"]
    transcript_version: str | None
    analysis_version: str | None
    reused_transcript: bool
    reused_analysis: bool


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def version_key(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x00".join(parts).encode("utf8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


async def analyze_media(
    *,
    file_path: Path,
    factory: sessionmaker[Session],
    scratch_dir: Path,
    platform: str,
    platform_video_id: str,
    author_platform_id: str,
    title: str,
    source_url: str,
    transcriber: Transcriber,
    generator: InsightGenerator,
    provenance: Literal["real_model", "test_fixture"] = "real_model",
) -> ProcessingOutcome:
    """Persist and reuse independent stage results, preserving old versions.

    Successful ASR and LLM caches are keyed by media hash, model ID, and prompt
    version. If downstream fails, ASR remains available for the next retry.
    """
    file_path = file_path.expanduser().resolve(strict=True)
    await asyncio.to_thread(probe_media, file_path)
    media_hash = await asyncio.to_thread(sha256_file, file_path)
    asr_model = getattr(transcriber, "model_version", None)
    llm_model = getattr(generator, "model", None)
    if not asr_model or not llm_model:
        raise ValueError("Transcriber.model_version and generator.model must be explicit for caching")
    transcript_version = version_key("asr", media_hash, asr_model, "pipeline-m1-v1", provenance)
    analysis_version = version_key("llm", transcript_version, llm_model, "prompt-m1-v1", provenance)

    with factory.begin() as session:
        video = session.scalar(select(VideoRecord).where(
            VideoRecord.platform == platform, VideoRecord.platform_video_id == platform_video_id,
        ))
        if video is None:
            video = VideoRecord(platform=platform, platform_video_id=platform_video_id,
                                author_platform_id=author_platform_id, title=title,
                                source_url=source_url)
            session.add(video)
            session.flush()
        elif video.author_platform_id != author_platform_id:
            raise ValueError("Creator identity conflicts with stored video record")
        # Never reuse previously derived results for a different media fingerprint.
        video.media_path = str(file_path)
        video.media_sha256 = media_hash
        video.processing_status = "media_ready"
        video_id = video.id
        previous_analysis = session.scalar(select(VideoAnalysis).where(
            VideoAnalysis.video_id == video.id, VideoAnalysis.analysis_version == analysis_version,
        ))
        if previous_analysis:
            video.processing_status = "analyzed"
            return ProcessingOutcome(video_id, "analyzed", transcript_version,
                                     analysis_version, True, True)
        cached_segments = list(session.scalars(select(TranscriptSegment).where(
            TranscriptSegment.video_id == video_id,
            TranscriptSegment.transcript_version == transcript_version,
        ).order_by(TranscriptSegment.segment_id)))

    reused_transcript = bool(cached_segments)
    if not reused_transcript:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        audio_path = scratch_dir / f"{video_id}-{media_hash[:12]}.wav"
        try:
            audio = await asyncio.to_thread(extract_audio, file_path, audio_path)
            if audio is None:
                with factory.begin() as session:
                    session.get(VideoRecord, video_id).processing_status = "no_speech"
                return ProcessingOutcome(video_id, "no_speech", None, None, False, False)
            try:
                result = await asyncio.to_thread(transcriber.transcribe, audio)
            finally:
                audio_path.unlink(missing_ok=True)
        except Exception:
            with factory.begin() as session:
                session.get(VideoRecord, video_id).processing_status = "transcription_failed"
            raise
        if result.model_version != asr_model:
            raise ValueError("ASR model version changed during the run")
        if not result.segments:
            with factory.begin() as session:
                session.get(VideoRecord, video_id).processing_status = "no_speech"
            return ProcessingOutcome(video_id, "no_speech", None, None, False, False)
        with factory.begin() as session:
            for part in result.segments:
                if part.end_ms <= part.start_ms or part.start_ms < 0 or not part.text.strip():
                    raise ValueError("ASR contains invalid segment")
                session.add(TranscriptSegment(
                    video_id=video_id, transcript_version=transcript_version,
                    segment_id=part.segment_id, start_ms=part.start_ms,
                    end_ms=part.end_ms, text=part.text,
                    model_version=asr_model[:120],
                ))
            session.get(VideoRecord, video_id).processing_status = "transcribed"

    with factory() as session:
        segments = list(session.scalars(select(TranscriptSegment).where(
            TranscriptSegment.video_id == video_id,
            TranscriptSegment.transcript_version == transcript_version,
        ).order_by(TranscriptSegment.segment_id)))
    if not segments:
        raise RuntimeError("Transcript cache unexpectedly empty")
    try:
        draft = await generator.generate(segments)
        anchored = anchor_insight(draft, video_id, transcript_version, segments, provenance)
    except Exception:
        with factory.begin() as session:
            session.get(VideoRecord, video_id).processing_status = "analysis_failed"
        raise
    with factory.begin() as session:
        session.add(VideoAnalysis(
            video_id=video_id, analysis_version=analysis_version,
            transcript_version=transcript_version, model_id=llm_model[:200],
            result=anchored.model_dump(mode="json"),
        ))
        session.get(VideoRecord, video_id).processing_status = "analyzed"
    return ProcessingOutcome(video_id, "analyzed", transcript_version,
                             analysis_version, reused_transcript, False)


async def analyze_local_file(
    path: Path, factory: sessionmaker[Session], scratch_dir: Path,
    transcriber: Transcriber, generator: InsightGenerator,
    provenance: Literal["real_model", "test_fixture"] = "real_model",
) -> ProcessingOutcome:
    if not path.is_file():
        raise FileNotFoundError(path)
    content_sha = await asyncio.to_thread(sha256_file, path)
    return await analyze_media(
        file_path=path, factory=factory, scratch_dir=scratch_dir,
        platform="local" if provenance == "real_model" else "test_fixture",
        platform_video_id=content_sha,
        author_platform_id="local-file-no-platform-author",
        title=path.name, source_url=f"local://sha256/{content_sha}",
        transcriber=transcriber, generator=generator, provenance=provenance,
    )
