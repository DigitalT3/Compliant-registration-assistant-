"""FR-16: no credential or client with write access to the live complaint system exists in the PoC, and nothing in it can reach that system."""
import socket
import subprocess

import pytest

from scripts import readonly_check as guard
from tests.conftest import EMP


def test_the_project_has_no_way_to_reach_the_complaint_system():
    assert guard.static_findings() == []


def test_no_route_looks_like_an_integration(client):
    paths = list(client.get("/openapi.json").json()["paths"])
    assert len(paths) > 40 and guard.route_findings(paths) == []
    assert guard.route_findings(["/api/sync", "/api/push-to-salesforce", "/api/webhook"]) != []


def test_the_guard_catches_each_way_in(tmp_path, monkeypatch):
    """The rules would fail if someone added a CRM client, a credential, a URL or a secret."""
    (tmp_path / "backend" / "services").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "requirements.txt").write_text("fastapi==1\nsimple-salesforce>=1.12\n")
    (tmp_path / "backend" / "sneaky.py").write_text('import requests\nimport os\nURL = "https://acme.my.salesforce.com/services"\nTOKEN = os.environ.get("SALESFORCE_TOKEN")\n')
    (tmp_path / "config.json").write_text('{"note": "writes to the CRM"}')
    (tmp_path / ".env.example").write_text("COMPLAINT_SYSTEM_PASSWORD=x\n")
    (tmp_path / "leak.txt").write_text("key " + "AKIA" + "ABCDEFGHIJKLMNOP" + "\n")      # assembled here so no real-looking key sits in this file
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    found = "\n".join(guard.static_findings())
    for expected in ("1. library not on the allowed list: simple-salesforce", "2. network library imported outside the database and AI modules: backend/sneaky.py",
                     "3. complaint-system term 'salesforce'", "3. complaint-system term 'CRM'", "4. URL to another host in backend/sneaky.py: acme.my.salesforce.com",
                     "5. environment variable read by the code is not on the known list: SALESFORCE_TOKEN",
                     "5. key in .env.example is not on the known list: COMPLAINT_SYSTEM_PASSWORD", "6. secret-like text in tracked file leak.txt"):
        assert expected in found, expected


def test_only_the_known_credentials_exist():
    store, ai, app = guard.ENV_STORE, guard.ENV_AI, guard.ENV_APP
    assert not (store & ai or store & app or ai & app)
    assert store == {"POC_DB", "POC_DB_PATH", "POC_PG_SCHEMA", "DATABASE_URL"}                    # the PoC's own store, nothing else
    secrets = {k for k in guard.ALLOWED_ENV if any(w in k for w in ("PASSWORD", "SECRET", "KEY", "TOKEN", "URL"))}
    assert secrets == {"DATABASE_URL", "AI_BASE_URL", "AI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AUTH_SECRET", "POC_ADMIN_PASSWORD", "CHECK_PASSWORD", "CHECK_RATER_PASSWORD"}


def test_a_whole_registration_and_the_admin_screens_open_no_connection_to_another_machine(client, monkeypatch):
    """With the mock model and the local database, nothing leaves the process: every socket connect is recorded."""
    seen = []
    real_connect, real_ex = socket.socket.connect, socket.socket.connect_ex

    def spy(self, address, *a, **k):
        seen.append(address)
        return real_connect(self, address, *a, **k)

    def spy_ex(self, address, *a, **k):
        seen.append(address)
        return real_ex(self, address, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", spy)
    monkeypatch.setattr(socket.socket, "connect_ex", spy_ex)
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    card = client.get("/api/customers/search", params={"q": "100001"}, headers=EMP).json()["candidates"][0]
    client.post("/api/prefill", headers=EMP, json={"customer_id": card["customer_id"], "origin": "search", "guess_site": True, "session_id": sid})
    client.post("/api/complaints/extract", headers=EMP, json={"text": "Container BOX-001-1 niet geleegd, klant 100001."})
    client.post("/api/complaints/classify", headers=EMP, json={"text": "Container missed again.", "session_id": sid})
    saved = client.post("/api/complaints", headers=EMP, json={"customer_id": "C001", "site_id": "C001-S1", "channel": "phone", "complaint_type": "service",
                                                           "root_cause": "missed", "description": "Again.", "session_id": sid,
                                                           "repeat_decisions": [{"prior_complaint_id": "COM-SEED-1", "decision": "reject", "reason": "Different container"}]})
    assert saved.status_code == 201
    admin = {"X-Demo-User": "demo.admin"}
    for path in ("/api/audit/records", f"/api/audit/records/{saved.json()['id']}", "/api/export/records.csv", "/api/analytics/summary", "/api/readout", "/api/export/disputes.csv"):
        assert client.get(path, headers=admin).status_code == 200
    assert seen == [], f"connections opened: {seen}"
