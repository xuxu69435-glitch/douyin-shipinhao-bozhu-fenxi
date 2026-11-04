from fastapi.testclient import TestClient

from app.main import create_app
from app.models import TaskRecord


def test_interrupted_states_recover(tmp_path, auth):
    app = create_app(tmp_path, auth["X-Analyst-Token"])
    with app.state.session_factory.begin() as session:
        session.add_all([
            TaskRecord(input_text="1", source_url="x", source_kind="profile", max_videos=10, status="pausing"),
            TaskRecord(input_text="2", source_url="x", source_kind="profile", max_videos=10, status="cancelling"),
            TaskRecord(input_text="3", source_url="x", source_kind="profile", max_videos=10, status="running"),
        ])
    with TestClient(app):
        with app.state.session_factory() as session:
            statuses = {t.input_text: t.status for t in session.query(TaskRecord).all()}
            assert statuses["1"] == "paused"
            assert statuses["2"] == "cancelled"
            assert statuses["3"] in ("queued", "running", "blocked")
