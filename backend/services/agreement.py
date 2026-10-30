"""People agreeing to one exact version of something (the cause list, a proposed list): review, agree or request changes.

A review counts for one content hash. When the content changes, earlier reviews stay as history but no longer count, so
"agreed" always means agreed to what is on screen now. Reviews live in ``app_settings`` under a key and every one is audited.
"""
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError

DECISIONS = {"agree", "changes"}


def _load(conn, key: str) -> list:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else []


# PUBLIC_INTERFACE
def status(conn, key: str, here: str, required: int, counting_roles: tuple | None = None) -> dict:
    """``draft``, ``changes_requested`` or ``agreed`` for the content with hash ``here`` (needs ``required`` agreements, no open change request).

    With ``counting_roles`` only reviews by people in those roles count towards the state (an administrator may review too, and is
    shown, but is not one of the named owners); every review says whether it counts.
    """
    latest: dict = {}
    for r in _load(conn, key):                              # one entry per person: their latest review, whatever the version
        latest[r["user_id"]] = r
    counts = lambda r: counting_roles is None or r.get("role") in counting_roles
    now = [r for r in latest.values() if r["content_hash"] == here and counts(r)]
    agreed = [r for r in now if r["decision"] == "agree"]
    state = "changes_requested" if any(r["decision"] == "changes" for r in now) else "agreed" if len(agreed) >= required else "draft"
    reviews = sorted(({"user_id": r["user_id"], "name": r["name"], "decision": r["decision"], "comment": r.get("comment"),
                       "at": r["at"], "current": r["content_hash"] == here, "role": r.get("role"), "counts": counts(r)} for r in latest.values()), key=lambda r: r["at"], reverse=True)
    return {"state": state, "required": required, "agreed": len(agreed), "content_hash": here, "reviews": reviews,
            "agreed_at": max(r["at"] for r in agreed) if state == "agreed" else None}


# PUBLIC_INTERFACE
def review(conn, user: dict, key: str, here: str, decision: str, comment: str | None, actions: tuple, extra: dict | None = None) -> None:
    """Record the user's review of the content as it is now (replaces their earlier one) and audit it. ``actions`` = (agree, changes) audit names."""
    if decision not in DECISIONS:
        raise ApiError(422, "invalid_decision", "decision must be 'agree' or 'changes'.")
    comment = (comment or "").strip()
    if decision == "changes" and not comment:
        raise ApiError(422, "comment_required", "Say what should change.")
    entry = {"user_id": user["id"], "name": user["name"], "role": user.get("role"), "decision": decision, "comment": comment[:500] or None, "at": db.now(), "content_hash": here}
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(_load(conn, key) + [entry], ensure_ascii=False)))
    audit(conn, user["id"], actions[0] if decision == "agree" else actions[1], {"content_hash": here, "comment": entry["comment"], **(extra or {})})
    conn.commit()


# PUBLIC_INTERFACE
def carry_over(conn, from_key: str, from_hash: str, to_key: str, to_hash: str, note: str) -> int:
    """Copy the agreements given to one version of something to another that is meant to be the same list (for example a proposal that became live)."""
    mine = [r for r in _load(conn, from_key) if r["content_hash"] == from_hash and r["decision"] == "agree"]
    latest: dict = {}
    for r in mine:
        latest[r["user_id"]] = r
    if not latest:
        return 0
    copied = [{**r, "content_hash": to_hash, "comment": note, "at": db.now()} for r in latest.values()]
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (to_key, json.dumps(_load(conn, to_key) + copied, ensure_ascii=False)))
    conn.commit()
    return len(copied)
