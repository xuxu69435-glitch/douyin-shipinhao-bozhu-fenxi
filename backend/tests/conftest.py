from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def auth():
    return {"X-Analyst-Token": "testing-local-app-token-123456789"}


@pytest.fixture
def client(tmp_path: Path, auth):
    app = create_app(tmp_path, auth["X-Analyst-Token"])
    with TestClient(app) as test_client:
        yield test_client
