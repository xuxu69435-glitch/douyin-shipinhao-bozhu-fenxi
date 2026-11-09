"""Versioned API schemas. No conclusion without source evidence."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateTask(BaseModel):
    input_text: str = Field(min_length=1, max_length=5000)
    max_videos: Literal[10, 30] = 10


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_url: str
    source_kind: str
    platform_id: str | None
    max_videos: int
    status: str
    phase: str
    success_count: int
    failure_count: int
    no_speech_count: int
    stop_reason: str | None
    error_code: str | None
    error_message: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    stage: Literal["M0"] = "M0"
    version: str = "0.1.2"


class EvidenceRef(BaseModel):
    video_id: str
    transcript_version: str
    segment_id: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class VideoInsight(BaseModel):
    summary: str
    primary_domain: str
    secondary_topics: list[str]
    content_format: str
    key_claims: list[str]
    explicitly_stated_preferences: list[str]
    citations: list[EvidenceRef]


class VideoView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    platform_video_id: str
    author_platform_id: str
    title: str
    source_url: str
    processing_status: str
    media_sha256: str | None


class SegmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_id: str
    transcript_version: str
    segment_id: int
    start_ms: int
    end_ms: int
    text: str
    model_version: str


class SubtitleExport(BaseModel):
    filename: str
    content: str
    format: Literal["srt", "vtt"]
