"""Shared fixtures: isolated seeded temp DB and API client."""
import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.services import ai


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("POC_DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.delenv("AI_MOCK_FAIL", raising=False)
    monkeypatch.delenv("POC_CLOCK_MODE", raising=False)
    ai.set_provider(None)
    seed.reset()
    from backend.app import create_app
    with TestClient(create_app()) as c:
        yield c
    ai.set_provider(None)


EMP = {"X-Demo-User": "demo.emp.a1"}
ADMIN = {"X-Demo-User": "demo.admin"}
