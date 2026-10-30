"""Confirming or disputing a repeat link (FR-13): stored next to the rule result, never changing it, for review by the rule owner."""
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
        "p.root_cause AS prior_cause, p.created AS prior_created, p.status AS prior_status "
        "FROM repeat_disputes d LEFT JOIN users u ON u.id=d.actor LEFT JOIN complaints c ON c.id=d.complaint_id "
        "LEFT JOIN customers cu ON cu.id=c.customer_id LEFT JOIN sites s ON s.id=c.site_id "
        "LEFT JOIN complaints p ON p.id=d.prior_complaint_id ORDER BY d.id DESC").fetchall()
    return [dict(r) for r in rows]
