"""M2 synthetic evidence aggregation tests, not real Douyin research."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import TaskRecord, TaskVideoRecord, TranscriptSegment, VideoAnalysis, VideoRecord
from app.reporting import ReportNotReady, build_creator_report, canonical_label


def insert_fixture(factory):
    with factory.begin() as session:
        task = TaskRecord(input_text="fixture", source_url="https://www.douyin.com/user/creator-test",
                          source_kind="profile", platform_id="creator-test", max_videos=10,
                          stop_reason="end_of_list")
        session.add(task)
        session.flush()
        for j, (domain, topic) in enumerate((("科技", "AI工具"), ("科技数码", "人工智能工具"), ("生活", "旅游"))):
            video = VideoRecord(platform_video_id=f"700000000000000000{j}", author_platform_id="creator-test",
                                source_url=f"https://www.douyin.com/video/700000000000000000{j}",
                                processing_status="analyzed")
            session.add(video)
            session.flush()
            session.add(TaskVideoRecord(task_id=task.id, video_id=video.id, status="completed"))
            session.add(TranscriptSegment(video_id=video.id, transcript_version="test-transcript-v1",
                                          segment_id=0, start_ms=1000, end_ms=2400, text="讨论一个技术点", model_version="fixture"))
            ref = {"video_id": video.id, "transcript_version": "test-transcript-v1",
                   "segment_id": 0, "start_ms": 1000, "end_ms": 2400}
            result = {
                "summary": "谈到一个话题", "summary_evidence": [ref],
                "primary_domain": domain, "secondary_topics": [topic], "content_format": "解说",
                "key_claims": [{"text": "讨论了技术", "speaker_role": "narrator",
                                "attribution_basis": "未核实叙述者身份",
                                "creator_identity_verified": False, "evidence": [ref]}],
                "explicitly_stated_preferences": [{"text": "我喜欢某工具", "speaker_role": "creator",
                                                    "attribution_basis": "模型仅猜测是博主",
                                                    "creator_identity_verified": False, "evidence": [ref]}],
                "discussed_entities": [{"text": "某工具", "speaker_role": "narrator",
                                        "attribution_basis": "明确被提及",
                                        "creator_identity_verified": False, "evidence": [ref]}],
                "provenance": "test_fixture",
            }
            session.add(VideoAnalysis(video_id=video.id, analysis_version=f"test-analysis-{j}",
                                      transcript_version="test-transcript-v1", model_id="test-llm", result=result))
        session.flush()
        return task.id


def test_canonical_normalization():
    from app.reporting import DOMAIN_ALIASES, THEME_ALIASES
    assert canonical_label(" 科技数码 ", DOMAIN_ALIASES) == "科技"
    assert canonical_label("人工智能工具", THEME_ALIASES) == "AI工具"


def test_report_sums_are_computed_and_creator_preferences_not_fabricated(tmp_path):
    app = create_app(tmp_path, "test-xxxxxxxxxxxxxxxxxxxx")
    factory = app.state.session_factory
    task_id = insert_fixture(factory)
    with factory.begin() as session:
        row = build_creator_report(session, task_id)
        report_id = row.id
        assert row.result["sample"]["analyzed_count"] == 3
        assert row.result["main_directions"][0]["name"] == "科技"
        assert row.result["main_directions"][0]["count"] == 2
        assert row.result["main_directions"][0]["percentage"] == 66.67
        assert row.result["topic_tendencies"][0]["name"] == "AI工具"
        assert row.result["topic_tendencies"][0]["percentage"] == 66.67
        assert row.result["frequently_discussed_entities"][0]["count"] == 3
        assert row.result["creator_preferences_verified"] == []
        assert len(row.result["preferences_not_attributed_to_creator"]) == 3
        assert row.result["business_claim"] is None
        assert all(x["evidence"][0]["source_url"].startswith("https://www.douyin.com/video/")
                   for x in row.result["main_directions"])
    with factory.begin() as session:
        row2 = build_creator_report(session, task_id)
        assert row2.id == report_id

    headers = {"X-Analyst-Token": "test-xxxxxxxxxxxxxxxxxxxx"}
    with TestClient(app) as client:
        assert client.get(f"/api/tasks/{task_id}/reports", headers=headers).json()[0]["id"] == report_id
        markdown = client.get(f"/api/reports/{report_id}/export/md", headers=headers).json()["content"]
        assert "## 主要领域" in markdown
        assert "test_fixture" in markdown
        assert "无经过独立身份核实的博主本人偏好" in markdown
        payload = client.get(f"/api/reports/{report_id}/export/json", headers=headers).json()
        assert payload["format"] == "json"
        assert client.get(f"/api/reports/{report_id}", headers=headers).json()["sample"]["analyzed_count"] == 3
        assert client.get("/api/reports/missing", headers=headers).status_code == 404
        assert client.get(f"/api/reports/{report_id}/export/pdf", headers=headers).status_code == 404
        assert client.get(f"/api/reports/{report_id}").status_code == 401


def test_report_mismatch_fails_without_inventing_identity(tmp_path):
    app = create_app(tmp_path, "test-xxxxxxxxxxxxxxxxxxxx")
    task_id = insert_fixture(app.state.session_factory)
    with app.state.session_factory.begin() as session:
        video = session.scalar(select(VideoRecord))
        video.author_platform_id = "different-creator"
    with app.state.session_factory.begin() as session:
        try:
            build_creator_report(session, task_id)
        except ReportNotReady as exc:
            assert "不同作者ID" in str(exc)
        else:
            raise AssertionError("mixed creators must be rejected")


def test_old_report_is_rejected_if_transcript_evidence_disappears(tmp_path):
    from app.models import TranscriptSegment
    app = create_app(tmp_path, "test-xxxxxxxxxxxxxxxxxxxx")
    task_id = insert_fixture(app.state.session_factory)
    with app.state.session_factory.begin() as session:
        report_id = build_creator_report(session, task_id).id
        first = session.scalar(select(TranscriptSegment))
        session.delete(first)
    headers = {"X-Analyst-Token": "test-xxxxxxxxxxxxxxxxxxxx"}
    with TestClient(app) as client:
        assert client.get(f"/api/reports/{report_id}", headers=headers).status_code == 409
        assert client.get(f"/api/reports/{report_id}/export/md", headers=headers).status_code == 409
