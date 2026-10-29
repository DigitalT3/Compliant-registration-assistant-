"""Server-side session and event recording (FR-15). Timestamps are server-stamped."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from .. import db, settings
from ..dbutil import audit
from ..errors import ApiError

STEPS = ["find_customer", "review_details", "describe_complaint", "classify", "repeat_save"]
ORIGINS = {"prefilled", "default", "suggested", "manual", "edited", "blank"}
EVENT_TYPES = {"step_entered", "step_completed", "field", "validation_failed"}


# PUBLIC_INTERFACE
def start(conn, user: dict, scenario: str | None = None, mode: str = "assistant",
          participant_id: str | None = None, opened_seconds_ago: float = 0) -> dict:
    """Create a session and record entry into the first step.

    ``mode`` is ``assistant`` (AI-assisted flow) or ``plain`` (form only, for like-for-like timing);
    ``participant_id`` tags the test participant for the timed user test. The session is created when the
    customer is chosen, so the client says how long the form had been open (an elapsed time, immune to
    clock differences); the session starts that long before, limited to the per-visit idle cap, so the
    time spent finding the customer is part of the registration time.
    """
    if mode not in ("assistant", "plain"):
        raise ApiError(422, "invalid_mode", "mode must be 'assistant' or 'plain'.")
    sid, created = str(uuid.uuid4()), db.now()
    cap = settings.get_config()["metrics"].get("step_idle_cap_seconds") or 3600
    back = max(0.0, min(float(opened_seconds_ago or 0), cap))
    now = (datetime.fromisoformat(created) - timedelta(seconds=back)).isoformat() if back else created
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
    if row["status"] == "abandoned" and not row["failure_status"] and row["actor"] == user["id"]:
        return _resume(conn, row)
    if row["status"] != "active":
        raise ApiError(409, "session_closed", f"Session is {row['status']}.")
    return dict(row)


def _resume(conn, row) -> dict:
    """The employee came back to a form the idle sweep had closed: carry on with the same session.

    Only a session closed by the sweep (no failure reason) and only by its owner. The step being worked on is
    closed and re-entered now, so the idle gap counts at most the per-visit cap, and ``session_resumed`` in the
    audit log marks the session (its total time includes the gap).
    """
    now = db.now()
    conn.execute("UPDATE sessions SET status='active',ended=NULL WHERE id=?", (row["id"],))
    step = row["current_step"] or STEPS[0]
    for kind in ("step_completed", "step_entered"):
        conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)", (row["id"], step, kind, now))
    audit(conn, row["actor"], "session_resumed", {"session_id": row["id"], "idle_since": row["ended"]})
    conn.commit()           # on its own: the complaint save that follows opens its own transaction
    return {**dict(row), "status": "active", "ended": None}


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


# Step names recorded before "check_repeats" and "review_save" became one screen count as the merged step.
LEGACY_STEPS = {"check_repeats": "repeat_save", "review_save": "repeat_save"}


# PUBLIC_INTERFACE
def step_durations(events: list, ended: str | None, cap: float | None = None) -> dict:
    """Seconds per step derived from recorded timestamps (entered to completed/next entered/end).

    Each visit to a step counts at most ``cap`` seconds (default ``metrics.step_idle_cap_seconds``), so a
    browser tab left open overnight does not turn one step into hours. The cap is per visit: going back and
    forth adds the visits up. Steps recorded under their old names are counted under the current step.
    """
    if cap is None:
        cap = settings.get_config()["metrics"].get("step_idle_cap_seconds")
    out, cur = {}, None

    def close_at(ts):
        nonlocal cur
        if cur:
            d = (datetime.fromisoformat(ts) - datetime.fromisoformat(cur[1])).total_seconds()
            d = max(d, 0)
            out[cur[0]] = out.get(cur[0], 0) + (min(d, cap) if cap else d)
            cur = None

    for e in events:
        step = LEGACY_STEPS.get(e["step"], e["step"])
        if e["event_type"] == "step_entered":
            close_at(e["at"])
            cur = (step, e["at"])
        elif cur and step == cur[0]:
            close_at(e["at"])
    if ended:
        close_at(ended)
    return {k: round(v, 3) for k, v in out.items()}
