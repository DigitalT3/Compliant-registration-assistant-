"""Confirming or disputing a repeat link (FR-13): stored next to the rule result, never changing it, for review by the rule owner."""
import json
from datetime import datetime, timedelta, timezone

from .. import db
from ..dbutil import audit
from ..errors import ApiError

DEFAULT_CONFIRM_REASON = "Confirmed by user"


# PUBLIC_INTERFACE
def clean(decision: str, reason: str | None) -> str:
    """The reason to store: a dispute ("reject") needs one of at least 3 characters; a confirmation gets a default."""
    text = (reason or "").strip()
    if len(text) >= 3:
        return text
    if decision == "reject":
        raise ApiError(422, "reason_required", "Say why this is not a repeat (at least 3 characters).")
    return DEFAULT_CONFIRM_REASON


# PUBLIC_INTERFACE
def insert(conn, actor_id: str, complaint_id: str, prior_id: str, decision: str, reason: str) -> None:
    """Store one decision with the rule evidence of the complaint's latest repeat check (does not commit)."""
    chk = conn.execute("SELECT id,rule_version,explanation FROM repeat_checks WHERE complaint_id=? ORDER BY id DESC LIMIT 1",
                       (complaint_id,)).fetchone()
    if not chk:
        raise ApiError(404, "repeat_check_not_found", "No stored repeat check for this complaint.")
    conn.execute("INSERT INTO repeat_disputes(repeat_check_id,complaint_id,prior_complaint_id,decision,reason,actor,"
                 "rule_version,evidence,at) VALUES(?,?,?,?,?,?,?,?,?)",
                 (chk["id"], complaint_id, prior_id, decision, reason, actor_id, chk["rule_version"], chk["explanation"], db.now()))
    audit(conn, actor_id, "repeat_match_disputed" if decision == "reject" else "repeat_match_confirmed",
          {"complaint_id": complaint_id, "prior_complaint_id": prior_id, "decision": decision, "reason": reason})


# PUBLIC_INTERFACE
def listing(conn) -> list:
    """Every decision with who, when, the complaint and the earlier complaint it concerns (for the rule owner's review)."""
    rows = conn.execute(
        "SELECT d.id, d.at, d.complaint_id, d.prior_complaint_id, d.decision, d.reason, d.actor, d.rule_version, d.evidence, "
        "u.name AS actor_name, cu.name AS customer_name, s.name AS site_name, c.root_cause AS cause, "
        "p.root_cause AS prior_cause, p.created AS prior_created, p.status AS prior_status, "
        "d.reviewed_at, d.review_note, rv.name AS reviewed_by_name "
        "FROM repeat_disputes d LEFT JOIN users u ON u.id=d.actor LEFT JOIN users rv ON rv.id=d.reviewed_by LEFT JOIN complaints c ON c.id=d.complaint_id "
        "LEFT JOIN customers cu ON cu.id=c.customer_id LEFT JOIN sites s ON s.id=c.site_id "
        "LEFT JOIN complaints p ON p.id=d.prior_complaint_id ORDER BY d.id DESC").fetchall()
    return [dict(r) for r in rows]


REVIEW_KEY, REVIEW_EVERY_DAYS = "dispute_review_last", 7


def _last(conn):
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (REVIEW_KEY,)).fetchone()
    return json.loads(row[0]) if row else None


# PUBLIC_INTERFACE
def review_status(conn) -> dict:
    """Where the weekly review stands: disputes waiting, when and by whom it was last done, and whether it is due.

    Only disputes ("reject") need review; confirmations are shown but never wait. Due = something is waiting and the last review
    was at least 7 days ago (or there was none).
    """
    pending = conn.execute("SELECT count(*) FROM repeat_disputes WHERE decision='reject' AND reviewed_at IS NULL").fetchone()[0]
    last = _last(conn)
    age = None
    if last:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["at"])).total_seconds() / 86400
    due = pending > 0 and (age is None or age >= REVIEW_EVERY_DAYS)
    return {"pending": pending, "last_review_at": last and last["at"], "last_review_by": last and last["by"], "every_days": REVIEW_EVERY_DAYS,
            "due": due, "next_due": None if not last else (datetime.fromisoformat(last["at"]) + timedelta(days=REVIEW_EVERY_DAYS)).isoformat()}


# PUBLIC_INTERFACE
def mark_reviewed(conn, user: dict, note: str | None) -> dict:
    """Record the weekly review: every decision not yet reviewed gets the time, the reviewer and the note (does not change the decisions)."""
    now, note = db.now(), (note or "").strip() or None
    done = conn.execute("UPDATE repeat_disputes SET reviewed_at=?, reviewed_by=?, review_note=? WHERE reviewed_at IS NULL", (now, user["id"], note)).rowcount
    value = json.dumps({"at": now, "by": user["name"], "note": note})
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (REVIEW_KEY, value))
    audit(conn, user["id"], "repeat_disputes_reviewed", {"decisions": done, "note": note})
    conn.commit()
    return review_status(conn)
