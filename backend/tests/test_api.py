import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import TaskRecord, TaskVideoRecord, TranscriptSegment, VideoRecord


PROFILE = "https://www.douyin.com/user/MS4wLjABAAAA_TESTxyz123"
VIDEO = "https://www.douyin.com/video/7444000000000012345"


def wait_for(client, auth, task_id, expected="blocked"):
    for _ in range(120):
        record = client.get(f"/api/tasks/{task_id}", headers=auth).json()
        if record["status"] == expected:
            return record
        time.sleep(0.02)
    raise AssertionError(f"timeout waiting for {expected}: {record}")


def test_auth_health(client, auth):
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={"X-Analyst-Token": "bad"}).status_code == 401
    assert client.get("/api/health", headers=auth).json() == {"status": "ok", "stage": "M0", "version": "0.1.2"}


def test_task_persists_and_truthfully_blocks(client, auth):
    created = client.post("/api/tasks", json={"input_text": PROFILE, "max_videos": 30}, headers=auth)
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["max_videos"] == 30
    saved = wait_for(client, auth, task_id)
    assert saved["error_code"] == "R0_LIVE_COLLECTION_NOT_VERIFIED"
    assert saved["success_count"] == 0
    assert client.get("/api/tasks", headers=auth).json()[0]["id"] == task_id
    assert client.get("/api/tasks/missing", headers=auth).status_code == 404


def test_video_limit_is_one(client, auth):
    response = client.post("/api/tasks", json={"input_text": VIDEO, "max_videos": 30}, headers=auth)
    assert response.status_code == 201
    assert response.json()["source_kind"] == "video"
    assert response.json()["max_videos"] == 1


def test_reject_invalid_inputs(client, auth):
    for text in ["bad", "https://evil.example/video/7444000000000012345"]:
        assert client.post("/api/tasks", json={"input_text": text}, headers=auth).status_code == 422
    assert client.post("/api/tasks", json={"input_text": PROFILE, "max_videos": 50}, headers=auth).status_code == 422


def test_pause_resume_cancel(client, auth):
    task = client.post("/api/tasks", json={"input_text": PROFILE}, headers=auth).json()
    wait_for(client, auth, task["id"])
    pause = client.post(f"/api/tasks/{task['id']}/pause", headers=auth)
    assert pause.json()["status"] == "paused"
    resume = client.post(f"/api/tasks/{task['id']}/resume", headers=auth)
    assert resume.json()["status"] == "queued"
    wait_for(client, auth, task["id"])
    cancel = client.post(f"/api/tasks/{task['id']}/cancel", headers=auth)
    assert cancel.json()["status"] == "cancelled"
    assert client.post(f"/api/tasks/{task['id']}/resume", headers=auth).status_code == 409


def test_sqlite_persists_and_fk_cascade(tmp_path, auth):
    app = create_app(tmp_path, auth["X-Analyst-Token"])
    with TestClient(app) as c:
        task_id = c.post("/api/tasks", json={"input_text": PROFILE}, headers=auth).json()["id"]
        wait_for(c, auth, task_id)
        factory = app.state.session_factory
        with factory.begin() as session:
            video = VideoRecord(platform_video_id="7444000000000012345", author_platform_id="creator_1", source_url=VIDEO)
            session.add(video)
            session.flush()
            session.add(TaskVideoRecord(task_id=task_id, video_id=video.id, phase="download", status="failed", error_code="MEDIA_UNAVAILABLE"))
            session.add(TranscriptSegment(video_id=video.id, transcript_version="asr-v1", segment_id=0, start_ms=0, end_ms=1000, text="你好", model_version="test-fixture"))
    app2 = create_app(tmp_path, auth["X-Analyst-Token"])
    with TestClient(app2) as c:
        assert c.get(f"/api/tasks/{task_id}", headers=auth).status_code == 200
        factory2 = app2.state.session_factory
        with factory2.begin() as session:
            assert len(session.scalars(select(VideoRecord)).all()) == 1
            video = session.scalars(select(VideoRecord)).one()
            session.delete(video)
        with factory2() as session:
            assert session.scalars(select(TranscriptSegment)).all() == []
            assert session.scalars(select(TaskVideoRecord)).all() == []


def test_single_worker_can_cooperatively_pause(tmp_path, auth):
    async def slow_processor(_id, control):
        for _ in range(30):
            await asyncio.sleep(.02)
            await control.checkpoint()

    app = create_app(tmp_path, auth["X-Analyst-Token"], slow_processor)
    with TestClient(app) as c:
        task = c.post("/api/tasks", json={"input_text": PROFILE}, headers=auth).json()
        wait_for(c, auth, task["id"], "running")
        action = c.post(f"/api/tasks/{task['id']}/pause", headers=auth)
        assert action.json()["status"] in ("pausing", "paused")
        wait_for(c, auth, task["id"], "paused")
