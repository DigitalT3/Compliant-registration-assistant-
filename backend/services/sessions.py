"""Server-side session and event recording (FR-15). Timestamps are server-stamped."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from .. import db, settings
from ..dbutil import audit
from ..errors import ApiError

STEPS = ["find_customer", "review_details", "describe_complaint", "classify", "check_repeats", "review_save"]
ORIGINS = {"prefilled", "default", "suggested", "manual", "edited", "blank"}
EVENT_TYPES = {"step_entered", "step_completed", "field", "validation_failed"}


# PUBLIC_INTERFACE
def start(conn, user: dict, scenario: str | None = None, mode: str = "assistant",
          participant_id: str | None = None) -> dict:
    """Create a session and record entry into the first step.

    ``mode`` is ``assistant`` (AI-assisted flow) or ``plain`` (form only, for like-for-like timing);
    ``participant_id`` tags the test participant for the timed user test.
    """
    if mode not in ("assistant", "plain"):
        raise ApiError(422, "invalid_mode", "mode must be 'assistant' or 'plain'.")
    sid, now = str(uuid.uuid4()), db.now()
    conn.execute("INSERT INTO sessions(id,actor,started,status,current_step,scenario,user_group,mode,participant_id) "
                 "VALUES(?,?,?,?,?,?,?,?,?)", (sid, user["id"], now, "active", STEPS[0], scenario,
                                              user["user_group"], mode, (participant_id or "").strip() or None))
    conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)",
                 (sid, STEPS[0], "step_entered", now))
    conn.commit()
    return {"session_id": sid, "started": now, "status": "active", "mode": mode}


def get_open(conn, session_id: str, user: dict) -> dict:
    """Return an active session owned by ``user`` (admin may access all) or raise."""
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        raise ApiError(404, "session_not_found", "Session not found.")
    if row["actor"] != user["id"] and user["role"] != "admin":
        raise ApiError(403, "forbidden", "Session belongs to another user.")
    if row["status"] != "active":
        raise ApiError(409, "session_closed", f"Session is {row['status']}.")
    return dict(row)


# PUBLIC_INTERFACE
def add_event(conn, session_id: str, user: dict, ev: dict) -> dict:
    """Record a validated step or field event; the client never supplies timestamps."""
    get_open(conn, session_id, user)
    kind, now = ev["type"], db.now()
    if kind not in EVENT_TYPES:
        raise ApiError(422, "invalid_event", f"type must be one of {sorted(EVENT_TYPES)}")
    if kind in ("step_entered", "step_completed"):
        if ev.get("step") not in STEPS:
            raise ApiError(422, "invalid_step", f"step must be one of {STEPS}")
        conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)",
                     (session_id, ev["step"], kind, now))
        if kind == "step_entered":
            conn.execute("UPDATE sessions SET current_step=? WHERE id=?", (ev["step"], session_id))
    else:
        if not ev.get("field"):
            raise ApiError(422, "invalid_event", "field is required")
        origin = ev.get("origin")
        if kind == "field" and origin not in ORIGINS:
            raise ApiError(422, "invalid_origin", f"origin must be one of {sorted(ORIGINS)}")
        # Values are never stored (privacy): only whether the field was changed.
        conn.execute("INSERT INTO field_events(session_id,field,origin,event_type,changed,at) VALUES(?,?,?,?,?,?)",
                     (session_id, ev["field"][:50], origin, kind, int(bool(ev.get("changed"))), now))
    conn.commit()
    return {"recorded": True, "at": now}


# PUBLIC_INTERFACE
def close(conn, session_id: str, status: str, user: dict, failure: str | None = None) -> dict:
    """Close an active session as abandoned or failed (``saved`` only happens via complaint save)."""
    get_open(conn, session_id, user)
    if status not in ("abandoned", "failed"):
        raise ApiError(400, "invalid_outcome", "Only 'abandoned' or 'failed' can be set here; "
                       "'saved' is recorded by the backend when a complaint is saved.")
    now = db.now()
    conn.execute("UPDATE sessions SET status=?,ended=?,failure_status=? WHERE id=?",
                 (status, now, failure, session_id))
    audit(conn, user["id"], "session_" + status, {"session_id": session_id})
    conn.commit()
    return {"session_id": session_id, "status": status, "ended": now}


# PUBLIC_INTERFACE
def sweep_abandoned(conn) -> int:
    """Mark active sessions idle longer than the configured limit as abandoned. Returns count."""
    limit = datetime.now(timezone.utc) - timedelta(minutes=settings.abandon_after_minutes())
    n = 0
    for s in conn.execute("SELECT id,actor,started FROM sessions WHERE status='active'").fetchall():
        last = conn.execute("SELECT max(at) FROM (SELECT at FROM step_events WHERE session_id=? "
                            "UNION ALL SELECT at FROM field_events WHERE session_id=?)",
                            (s["id"], s["id"])).fetchone()[0] or s["started"]
        if datetime.fromisoformat(last) < limit:
            conn.execute("UPDATE sessions SET status='abandoned',ended=? WHERE id=?", (last, s["id"]))
            audit(conn, "system", "session_abandoned", {"session_id": s["id"], "swept": True})
            n += 1
    conn.commit()
    return n


# PUBLIC_INTERFACE
def step_durations(events: list, ended: str | None) -> dict:
    """Seconds per step derived from recorded timestamps (entered to completed/next entered/end)."""
    out, cur = {}, None

    def close_at(ts):
        nonlocal cur
        if cur:
            d = (datetime.fromisoformat(ts) - datetime.fromisoformat(cur[1])).total_seconds()
            out[cur[0]] = out.get(cur[0], 0) + max(d, 0)
            cur = None

    for e in events:
        if e["event_type"] == "step_entered":
            close_at(e["at"])
            cur = (e["step"], e["at"])
        elif cur and e["step"] == cur[0]:
            close_at(e["at"])
    if ended:
        close_at(ended)
    return {k: round(v, 3) for k, v in out.items()}
