"""Shared fixtures: isolated seeded temp DB and API client."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Tests never call a real model, whatever .env says (db.py loads .env on import).
os.environ["LLM_PROVIDER"] = ""
os.environ["POC_CLOCK_MODE"] = "fixed"      # .env may select the real clock; the scripted scenarios need the fixed one
os.environ["AI_PROVIDER"] = "mock"
os.environ["AI_TIMEOUT_S"] = "3.5"

from backend import db, seed
from backend.services import ai
from backend.settings import invalidate_config


PG_MODE = os.environ.get("POC_TEST_PG") == "1"
PG_SCHEMA = "t_" + uuid.uuid4().hex[:12]


@pytest.fixture(scope="session", autouse=True)
def postgres_schema():
    """Postgres mode only (POC_TEST_PG=1, needs DATABASE_URL): one throwaway schema for the whole
    run, dropped at the end. Each test empties and reseeds it, so seed.reset() can never touch
    the real project tables."""
    yield
    if PG_MODE:
        os.environ["POC_DB"] = "postgres"
        os.environ.pop("POC_PG_SCHEMA", None)
        with db._connect_pg() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{PG_SCHEMA}" CASCADE')


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    """Tests never touch a hosted database by accident: SQLite unless POC_TEST_PG=1. Demo accounts are on for tests."""
    monkeypatch.setenv("POC_DEMO_MODE", "1")
    invalidate_config()
    if PG_MODE:
        monkeypatch.setenv("POC_DB", "postgres")
        monkeypatch.setenv("POC_PG_SCHEMA", PG_SCHEMA)
    else:
        monkeypatch.setenv("POC_DB", "sqlite")
        monkeypatch.delenv("POC_PG_SCHEMA", raising=False)


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
