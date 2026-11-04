"""M1/M2 job integration with TEST-ONLY provider/ASR/LLM, never live Douyin."""

import subprocess
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.collector import AuthorWorks, VideoCandidate
from app.job_processor import LiveTaskProcessor, safe_error
from app.main import create_app
from app.models import CreatorReport, TaskVideoRecord, TranscriptSegment, VideoAnalysis
from app.transcription import AsrResult, AsrSegment

AUTHOR = "creatorTEST123"


class ProviderFixture:
    def __init__(self, missing_one=False):
        self.missing_one = missing_one

    async def profile_id(self, _url):
        return AUTHOR

    async def video_detail(self, _url):
        return self._videos()[0]

    def _videos(self):
        return [VideoCandidate(f"700000000000000000{i}", AUTHOR, f"测试作品{i}", None,
                               f"https://www.douyin.com/video/700000000000000000{i}",
                               None if self.missing_one and i == 0 else "https://www.douyinvod.com/public-test.mp4")
                for i in range(2)]

    async def author_works(self, _author_id, _max_videos):
        return AuthorWorks(AUTHOR, self._videos(), 2, "end_of_list", 1, self._videos()[1])


class ASRFixture:
    model_version = "test-only-asr"

    def transcribe(self, _audio):
        return AsrResult(self.model_version, (AsrSegment(0, 100, 1500, "我介绍人工智能工具。"),))


class LLMFixture:
    model = "test-only-llm"

    async def generate(self, _segments):
        return {
            "summary": "介绍人工智能工具", "summary_segment_ids": [0],
            "primary_domain": "人工智能", "secondary_topics": ["AI工具"],
            "content_format": "解说", "key_claims": [],
            "explicitly_stated_preferences": [], "discussed_entities": [],
        }


async def fake_media_download(_url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=128x96:r=4:d=2",
        "-f", "lavfi", "-i", "sine=frequency=800:sample_rate=16000:duration=2",
        "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(destination),
    ], capture_output=True, check=True, timeout=30)
    return {"size_bytes": destination.stat().st_size}


def until_done(client, headers, task_id):
    for _ in range(250):
        task = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        if task["status"] in {"completed", "failed", "blocked"}:
            return task
        time.sleep(0.02)
    raise AssertionError(task)


def test_profile_task_completes_real_ffmpeg_but_mocked_models(tmp_path):
    token = "test-xxxxxxx-yyyyyyyyy-zzzzzzz"
    headers = {"X-Analyst-Token": token}
    app = create_app(tmp_path, token)
    app.state.worker.processor = LiveTaskProcessor(
        app.state.session_factory, tmp_path, ProviderFixture(), ASRFixture(),
        LLMFixture(), fake_media_download, provenance="test_fixture",
    )
    with TestClient(app) as client:
        task = client.post("/api/tasks", headers=headers,
                           json={"input_text": f"https://www.douyin.com/user/{AUTHOR}", "max_videos": 10}).json()
        state = until_done(client, headers, task["id"])
        assert state["status"] == "completed"
        assert state["success_count"] == 2 and state["failure_count"] == 0
        assert state["stop_reason"] == "end_of_list"
        linked = client.get(f"/api/tasks/{task['id']}/videos", headers=headers).json()
        assert len(linked) == 2
        reports = client.get(f"/api/tasks/{task['id']}/reports", headers=headers).json()
        assert len(reports) == 1
        report = client.get(f"/api/reports/{reports[0]['id']}", headers=headers).json()
        assert report["provenance"] == "test_fixture"
        assert report["sample"]["analyzed_count"] == 2
        assert report["main_directions"][0]["percentage"] == 100.0
        with app.state.session_factory() as session:
            assert len(session.scalars(select(TranscriptSegment)).all()) == 2
            assert len(session.scalars(select(VideoAnalysis)).all()) == 2
            assert len(session.scalars(select(CreatorReport)).all()) == 1


def test_partial_failure_still_builds_honest_sample_report(tmp_path):
    token = "test-xxxxxxx-yyyyyyyyy-zzzzzzz"
    headers = {"X-Analyst-Token": token}
    app = create_app(tmp_path, token)
    app.state.worker.processor = LiveTaskProcessor(
        app.state.session_factory, tmp_path, ProviderFixture(missing_one=True),
        ASRFixture(), LLMFixture(), fake_media_download, provenance="test_fixture",
    )
    with TestClient(app) as client:
        task = client.post("/api/tasks", headers=headers,
                           json={"input_text": f"https://www.douyin.com/user/{AUTHOR}"}).json()
        done = until_done(client, headers, task["id"])
        assert done["status"] == "completed"
        assert done["success_count"] == 1 and done["failure_count"] == 1
        with app.state.session_factory() as session:
            failed = session.scalar(select(TaskVideoRecord).where(TaskVideoRecord.status == "failed"))
            assert "媒体地址" in failed.error_message
        report_meta = client.get(f"/api/tasks/{task['id']}/reports", headers=headers).json()[0]
        report = client.get(f"/api/reports/{report_meta['id']}", headers=headers).json()
        assert report["sample"]["failed_count"] == 1
        assert report["sample"]["analyzed_count"] == 1
        assert report["sample"]["collected_count"] == 2


def test_enabled_live_but_missing_explicit_opt_in_is_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv("ANALYST_ENABLE_LIVE", raising=False)
    token = "test-xxxxxxx-yyyyyyyyy-zzzzzzz"
    headers = {"X-Analyst-Token": token}
    app = create_app(tmp_path, token, enable_live=True)
    with TestClient(app) as client:
        task = client.post("/api/tasks", headers=headers,
                           json={"input_text": f"https://www.douyin.com/user/{AUTHOR}"}).json()
        state = until_done(client, headers, task["id"])
        assert state["status"] == "blocked"
        assert state["error_code"] == "LIVE_PIPELINE_CONFIG_BLOCKED"


def test_errors_are_redacted():
    exc = RuntimeError("could not GET https://cdn.douyin.com/file?token=secret123 Cookie:abcd")
    safe = safe_error(exc)
    assert "secret123" not in safe
    assert "abcd" not in safe


def test_completed_media_can_be_reused_when_new_cdn_address_is_missing(tmp_path):
    from dataclasses import replace
    from app.models import AnalysisRun
    class NoMediaAddress(ProviderFixture):
        async def author_works(self, author_id, max_videos):
            works = await super().author_works(author_id, max_videos)
            return replace(works, videos=[replace(video, media_url=None) for video in works.videos])
    token = "test-reuse-xxxxxxx-yyyyyyyyy-zzzzzzz"
    headers = {"X-Analyst-Token": token}
    app = create_app(tmp_path, token)
    factory = app.state.session_factory
    app.state.worker.processor = LiveTaskProcessor(factory, tmp_path, ProviderFixture(),
        ASRFixture(), LLMFixture(), fake_media_download, provenance="test_fixture")
    with TestClient(app) as client:
        first = client.post('/api/tasks', headers=headers,
                            json={'input_text': f'https://www.douyin.com/user/{AUTHOR}'}).json()
        assert until_done(client, headers, first['id'])['status'] == 'completed'
        with factory() as session:
            original_runs = len(session.scalars(select(AnalysisRun)).all())
        app.state.worker.processor.provider = NoMediaAddress()
        second = client.post('/api/tasks', headers=headers,
                             json={'input_text': f'https://www.douyin.com/user/{AUTHOR}'}).json()
        completed = until_done(client, headers, second['id'])
        assert completed['status'] == 'completed' and completed['success_count'] == 2
        with factory() as session:
            assert len(session.scalars(select(AnalysisRun)).all()) == original_runs
