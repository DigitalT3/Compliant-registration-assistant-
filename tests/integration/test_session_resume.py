"""An employee who comes back after a long pause can still save: the idle sweep must not lock them out."""
from backend import db
from tests.conftest import ADMIN, EMP

OTHER = {"X-Demo-User": "demo.emp.b1"}
BODY = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
        "root_cause": "missed", "description": "Container was not emptied."}


def idle_session(client, minutes=45):
    """Start a session, make its last activity `minutes` old, then let a dashboard view sweep it."""
    sid = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/events", headers=EMP, json={"type": "step_entered", "step": "review_details"})
    old = "2026-10-01T10:00:00+00:00"
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET started=? WHERE id=?", (old, sid))
        conn.execute("UPDATE step_events SET at=? WHERE session_id=?", (old, sid))
        conn.execute("UPDATE field_events SET at=? WHERE session_id=?", (old, sid))
        conn.commit()
    client.get("/api/analytics/summary", headers=ADMIN)                       # a dashboard view runs the sweep
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM sessions WHERE id=?", (sid,)).fetchone()[0] == "abandoned"
    return sid


def status(sid):
    with db.connect() as conn:
        return conn.execute("SELECT status FROM sessions WHERE id=?", (sid,)).fetchone()[0]


def test_saving_after_a_long_pause_resumes_the_session(client):
    sid = idle_session(client)
    r = client.post("/api/complaints", headers=EMP, json={**BODY, "session_id": sid})
    assert r.status_code == 201, r.text                                          # no more "Session is abandoned"
    assert status(sid) == "saved"
    with db.connect() as conn:
        a = conn.execute("SELECT actor,data FROM audit WHERE action='session_resumed'").fetchall()
    assert len(a) == 1 and sid in a[0]["data"]
    assert client.post("/api/complaints", headers=EMP, json={**BODY, "session_id": sid}).status_code == 409   # still saved only once


def test_any_action_in_the_session_resumes_it_and_it_is_not_swept_again_at_once(client):
    sid = idle_session(client)
    assert client.post(f"/api/sessions/{sid}/events", headers=EMP,
                       json={"type": "field", "field": "channel", "origin": "default"}).status_code == 200
    assert status(sid) == "active"
    client.get("/api/analytics/summary", headers=ADMIN)                           # the sweep runs again: the session is fresh now
    assert status(sid) == "active"


def test_only_the_owner_resumes_and_explicit_closes_stay_closed(client):
    sid = idle_session(client)
    assert client.post("/api/complaints", headers=OTHER, json={**BODY, "session_id": sid}).status_code == 403
    assert status(sid) == "abandoned"                                             # someone else cannot revive it
    closed = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    assert client.post(f"/api/sessions/{closed}/complete", headers=EMP, json={"outcome": "failed", "failure_status": "ai_failed"}).status_code == 200
    r = client.post("/api/complaints", headers=EMP, json={**BODY, "session_id": closed})
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_closed"
    deliberate = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    client.post(f"/api/sessions/{deliberate}/complete", headers=EMP, json={"outcome": "abandoned", "failure_status": "user_cancelled"})
    assert client.post("/api/complaints", headers=EMP, json={**BODY, "session_id": deliberate}).status_code == 409


def test_the_idle_gap_counts_at_most_the_cap_in_the_step_time(client):
    sid = idle_session(client)
    client.post("/api/complaints", headers=EMP, json={**BODY, "session_id": sid})
    row = next(i for i in client.get("/api/analytics/sessions", headers=ADMIN).json()["items"] if i["id"] == sid)
    assert row["status"] == "saved" and 600 <= row["step_seconds"].get("review_details", 0) <= 601        # the cap, plus the moments after resuming
