"""FR-10: "Other" cannot be saved without a reason."""
import pytest

from backend import db
from tests.conftest import ADMIN, EMP

BASE = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service", "description": "A seagull built a nest under the lid."}


def _count():
    with db.connect() as conn:
        return conn.execute("SELECT count(*) FROM complaints").fetchone()[0]


@pytest.mark.parametrize("reason", [None, "", "   ", "\n\t", ".", "..", "...", "!!!", "ab", " a "])
def test_other_without_a_real_reason_is_refused_and_nothing_is_saved(client, reason):
    before = _count()
    r = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": reason})
    assert r.status_code == 422 and r.json()["error"]["code"] == "other_reason_required"
    assert _count() == before


def test_a_refused_save_leaves_the_registration_open_to_be_fixed(client):
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    assert client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "session_id": sid}).status_code == 422
    ok = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": "Seagull nest", "session_id": sid})
    assert ok.status_code == 201                                                          # same session, now with a reason


@pytest.mark.parametrize("reason", ["abc", "  Seagull nest under the lid  ", "Wildlife", "Zwerfdier op locatie", "42 gulls"])
def test_other_with_a_reason_is_saved_trimmed(client, reason):
    saved = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": reason})
    assert saved.status_code == 201
    rec = client.get(f"/api/complaints/{saved.json()['id']}", headers=EMP).json()
    assert rec["root_cause"] == "other" and rec["other_reason"] == reason.strip() and rec["payload"]["other_reason"] == reason.strip()


def test_the_reason_can_be_500_characters_but_not_501(client):
    assert client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": "x" * 500}).status_code == 201
    assert client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": "x" * 501}).status_code == 422


def test_a_reason_only_belongs_to_other(client):
    saved = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed", "other_reason": "left over from an earlier choice"})
    rec = client.get(f"/api/complaints/{saved.json()['id']}", headers=EMP).json()
    assert rec["root_cause"] == "missed" and rec["other_reason"] is None and rec["payload"]["other_reason"] == ""


def test_saved_reasons_feed_the_other_analysis(client):
    for reason in ("Seagull nest", "seagull nest", "Broken gate"):
        client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other", "other_reason": reason})
    groups = client.get("/api/analysis/other-reasons", headers=ADMIN).json()["groups"]
    assert {"reason": "seagull nest", "count": 2} in groups


def test_there_is_no_other_way_to_change_a_saved_cause(client):
    saved = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed"}).json()["id"]
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/api/complaints/{saved}", headers=EMP).status_code in (404, 405)
