"""M1 deterministic injection tests: these are NOT real Whisper/LLM/Douyin runs."""

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.database import build_session_factory
from app.evidence import milliseconds_to_srt, subtitles_text
from app.insights import EvidenceIntegrityError, anchor_insight
from app.main import create_app
from app.models import TranscriptSegment, VideoAnalysis, VideoRecord
from app.pipeline import analyze_local_file
from app.transcription import AsrSegment, AsrResult, normalize_asr_segments


class FakeASR:
    model_version = "fixture-whisper-v1"
    calls = 0

    def transcribe(self, _audio):
        self.calls += 1
        return AsrResult(self.model_version, (
            AsrSegment(0, 100, 900, "我在研究人工智能工具。"),
            AsrSegment(1, 1000, 1800, "下面引用朋友的观点。"),
        ))


class FakeLLM:
    model = "fixture-openai-compatible"

    def __init__(self, invalid=False):
        self.calls = 0
        self.invalid = invalid

    async def generate(self, _segments):
        self.calls += 1
        return {
            "summary": "讨论AI工具并引用另一人的说法",
            "summary_segment_ids": [0, 1],
            "primary_domain": "科技",
            "secondary_topics": ["AI工具", "AI工具", "技术应用"],
            "content_format": "解说",
            "key_claims": [{"text": "谈到了AI工具", "speaker_role": "narrator",
                            "attribution_basis": "未核实是否为上传者", "segment_ids": [0]}],
            "explicitly_stated_preferences": [{"text": "朋友的说法不等于博主偏好", "speaker_role": "quoted",
                                                "attribution_basis": "有明确引用语句", "segment_ids": [1 if not self.invalid else 999]}],
        }


def media_file(tmp_path: Path, audio: bool = True) -> Path:
    path = tmp_path / ("talk_with_audio.mp4" if audio else "silent_video.mp4")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "color=c=black:s=128x96:r=4:d=2"]
    if audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=500:sample_rate=16000:duration=2"])
    command += ["-c:v", "mpeg4"]
    if audio:
        command += ["-c:a", "aac", "-shortest"]
    command.append(str(path))
    subprocess.run(command, check=True, capture_output=True, timeout=25)
    return path


def build_draft_segment():
    return [SimpleNamespace(video_id="v1", transcript_version="t1", segment_id=1,
                            start_ms=1_500, end_ms=2_500, text="证据片段")]


def test_normalize_asr_segments_and_srt():
    parts = [SimpleNamespace(start=0.12, end=1.45, text=" 你好 "),
             SimpleNamespace(start=1.50, end=1.80, text="  ")]
    normalized = normalize_asr_segments(parts, "whisper-test", "zh")
    assert normalized.segments == (AsrSegment(0, 120, 1450, "你好"),)
    assert milliseconds_to_srt(3_661_234) == "01:01:01,234"
    assert milliseconds_to_srt(3_661_234, vtt=True) == "01:01:01.234"
    assert normalized.language == "zh"
    with pytest.raises(ValueError):
        normalize_asr_segments([SimpleNamespace(start=2, end=1, text="bad")], "test")


def test_evidence_anchor_rejects_foreign_ids_and_fake_timestamps():
    raw = FakeLLM().__dict__  # not a valid model object
    with pytest.raises(ValidationError):
        anchor_insight(raw, "v1", "t1", build_draft_segment())

    valid = {
        "summary": "引用", "summary_segment_ids": [1], "primary_domain": "科技",
        "secondary_topics": ["AI"], "content_format": "解说",
        "key_claims": [], "explicitly_stated_preferences": [],
    }
    insight = anchor_insight(valid, "v1", "t1", build_draft_segment(), "test_fixture")
    assert insight.summary_evidence[0].start_ms == 1500
    assert insight.summary_evidence[0].end_ms == 2500
    assert insight.provenance == "test_fixture"
    with pytest.raises(EvidenceIntegrityError):
        anchor_insight(dict(valid, summary_segment_ids=[9]), "v1", "t1", build_draft_segment())
    with pytest.raises(ValidationError):
        anchor_insight(dict(valid, video_id="hallucinated"), "v1", "t1", build_draft_segment())
    with pytest.raises(EvidenceIntegrityError):
        anchor_insight(valid, "v1", "t1", [SimpleNamespace(**dict(build_draft_segment()[0].__dict__, video_id="other"))])


def test_local_video_real_ffmpeg_fake_asr_llm_caches_versions(tmp_path):
    path = media_file(tmp_path)
    factory, engine = build_session_factory(tmp_path / "db")
    asr = FakeASR()
    llm = FakeLLM()
    try:
        a = asyncio.run(analyze_local_file(path, factory, tmp_path / "work", asr, llm, "test_fixture"))
        b = asyncio.run(analyze_local_file(path, factory, tmp_path / "work", asr, llm, "test_fixture"))
        assert a.status == "analyzed"
        assert a.reused_analysis is False and a.reused_transcript is False
        assert b.reused_analysis is True and b.reused_transcript is True
        assert asr.calls == 1 and llm.calls == 1
        assert a.analysis_version == b.analysis_version
        with factory() as session:
            assert len(session.scalars(select(TranscriptSegment)).all()) == 2
            row = session.scalar(select(VideoAnalysis))
            assert row.result["explicitly_stated_preferences"][0]["speaker_role"] == "quoted"
            assert row.result["explicitly_stated_preferences"][0]["creator_identity_verified"] is False
            assert row.result["secondary_topics"] == ["AI工具", "技术应用"]
            assert session.scalar(select(VideoRecord)).platform == "test_fixture"
    finally:
        engine.dispose()


def test_invalid_llm_claim_preserves_asr_and_can_retry(tmp_path):
    factory, engine = build_session_factory(tmp_path / "db")
    asr = FakeASR()
    try:
        with pytest.raises(EvidenceIntegrityError):
            asyncio.run(analyze_local_file(media_file(tmp_path), factory, tmp_path / "work",
                                           asr, FakeLLM(invalid=True), "test_fixture"))
        assert asr.calls == 1
        with factory() as session:
            assert len(session.scalars(select(TranscriptSegment)).all()) == 2
            assert not session.scalars(select(VideoAnalysis)).all()
            assert session.scalar(select(VideoRecord)).processing_status == "analysis_failed"
        result = asyncio.run(analyze_local_file(media_file(tmp_path), factory, tmp_path / "work",
                                                asr, FakeLLM(), "test_fixture"))
        assert result.status == "analyzed" and result.reused_transcript is True
        assert asr.calls == 1
    finally:
        engine.dispose()


def test_local_silent_video_reports_no_audio(tmp_path):
    factory, engine = build_session_factory(tmp_path / "db")
    asr, llm = FakeASR(), FakeLLM()
    try:
        outcome = asyncio.run(analyze_local_file(media_file(tmp_path, False), factory,
                                                  tmp_path / "work", asr, llm, "test_fixture"))
        assert outcome.status == "no_speech" and outcome.transcript_version is None
        assert asr.calls == 0 and llm.calls == 0
    finally:
        engine.dispose()


def test_transcript_and_evidence_api(tmp_path):
    token = "testing-local-app-token-123456789"
    auth = {"X-Analyst-Token": token}
    path = media_file(tmp_path)
    app = create_app(tmp_path / "db", token)
    with TestClient(app) as client:
        result = asyncio.run(analyze_local_file(
            path, app.state.session_factory, tmp_path / "work", FakeASR(), FakeLLM(), "test_fixture"
        ))
        video_id = result.video_id
        version = result.transcript_version
        detail = client.get(f"/api/videos/{video_id}", headers=auth)
        assert detail.status_code == 200
        assert detail.json()["transcript_versions"] == [version]
        assert len(client.get("/api/videos", headers=auth).json()) == 1
        assert client.get("/api/videos", headers={}).status_code == 401
        subs = client.get(f"/api/videos/{video_id}/subtitles/{version}/srt", headers=auth).json()
        assert subs["content"].startswith("1\n00:00:00,100 --> 00:00:00,900\n")
        assert "WEBVTT" in client.get(f"/api/videos/{video_id}/subtitles/{version}/vtt", headers=auth).json()["content"]
        source = client.get(f"/api/videos/{video_id}/evidence/{version}/1", headers=auth).json()
        assert source["text"] == "下面引用朋友的观点。"
        analysis = client.get(f"/api/videos/{video_id}/analyses/{result.analysis_version}", headers=auth).json()
        assert analysis["summary_evidence"][0]["video_id"] == video_id
        assert client.get(f"/api/videos/{video_id}/evidence/{version}/999", headers=auth).status_code == 404
        assert client.get(f"/api/videos/{video_id}/subtitles/{version}/docx", headers=auth).status_code == 404
        assert client.get(f"/api/tasks/missing/videos", headers=auth).status_code == 404
