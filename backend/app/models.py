"""Task metadata and separate per-video / evidence-version persistence."""

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    input_text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(2048))
    source_kind: Mapped[str] = mapped_column(String(20))
    platform_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    max_videos: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(32), default="waiting_for_collector")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    no_speech_count: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class VideoRecord(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("platform", "platform_video_id", name="uq_platform_video"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(24), default="douyin")
    platform_video_id: Mapped[str] = mapped_column(String(200))
    author_platform_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    media_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(25), default="discovered")


class TaskVideoRecord(Base):
    __tablename__ = "task_videos"
    __table_args__ = (UniqueConstraint("task_id", "video_id", name="uq_task_video"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    phase: Mapped[str] = mapped_column(String(35), default="discovered")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("video_id", "transcript_version", "segment_id", name="uq_segment_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    transcript_version: Mapped[str] = mapped_column(String(80))
    segment_id: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(120))


class VideoAnalysis(Base):
    __tablename__ = "video_analyses"
    __table_args__ = (UniqueConstraint("video_id", "analysis_version", name="uq_analysis_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    analysis_version: Mapped[str] = mapped_column(String(80))
    transcript_version: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(String(200))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CreatorReport(Base):
    __tablename__ = "creator_reports"
    __table_args__ = (UniqueConstraint("task_id", "report_version", name="uq_report_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    report_version: Mapped[str] = mapped_column(String(80))
    evidence_version: Mapped[str] = mapped_column(String(80))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


Index("ix_segments_lookup", TranscriptSegment.video_id, TranscriptSegment.transcript_version, TranscriptSegment.start_ms)
