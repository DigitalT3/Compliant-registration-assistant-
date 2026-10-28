"""Complaint validation and ATOMIC persistence to the PoC database only (FR-14, FR-16).

Nothing here talks to any external system: there is no live-system write path.
"""
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import causes_by_id, get_config
from . import repeat as repeat_svc
from . import sessions as sessions_svc


def load_history(conn, customer_id: str, exclude: str | None = None) -> list:
    """Previous complaints of a customer (repeat evidence candidates)."""
    return [dict(r, created=r["created"]) for r in conn.execute(
        "SELECT id,customer_id,site_id,root_cause,created,status FROM complaints "
        "WHERE customer_id=? AND id IS NOT ?", (customer_id, exclude))]


# PUBLIC_INTERFACE
def check_repeat(conn, cand: dict, session_id: str | None = None, complaint_id: str | None = None) -> dict:
    """Evaluate the active repeat rule against stored history and persist the evidence."""
    cfg = get_config()
    result = repeat_svc.evaluate_repeat(cfg["repeat_rule"], cand, load_history(conn, cand["customer_id"]) if cand.get("customer_id") else [],
                                        db.reference_now(), causes_by_id(cfg))
    _insert_repeat_check(conn, session_id, complaint_id, result)
    return result


def _insert_repeat_check(conn, session_id, complaint_id, result) -> None:
    conn.execute("INSERT INTO repeat_checks(session_id,complaint_id,rule_version,input_hash,is_repeat,"
                 "matching_ids,explanation,checked_at) VALUES(?,?,?,?,?,?,?,?)",
                 (session_id, complaint_id, result["rule_version"], result["input_hash"], int(result["is_repeat"]),
                  json.dumps([m["id"] for m in result["matches"]]), json.dumps(result), db.now()))


def _validate(conn, p: dict, cfg: dict) -> None:
    missing = [f for f in cfg["required_fields"] if not str(p.get(f) or "").strip()]
    if missing:
        raise ApiError(422, "missing_required_fields", "Required fields missing.", {"fields": missing})
    if p["complaint_type"] not in {t["id"] for t in cfg["types"]}:
        raise ApiError(422, "invalid_type", "Unknown complaint type.")
    if p["root_cause"] not in causes_by_id(cfg):
        raise ApiError(422, "invalid_root_cause", "Root cause is not in the active taxonomy.")
    if p["root_cause"] == "other" and not (p.get("other_reason") or "").strip():
        raise ApiError(422, "other_reason_required", "A reason is required when 'Other' is selected.")
    if not conn.execute("SELECT 1 FROM customers WHERE id=?", (p["customer_id"],)).fetchone():
        raise ApiError(422, "invalid_customer", "Unknown customer.")
    for field, table in (("site_id", "sites"), ("contract_id", "contracts"), ("order_id", "orders")):
        if p.get(field) and not conn.execute(f"SELECT 1 FROM {table} WHERE id=? AND customer_id=?",
                                             (p[field], p["customer_id"])).fetchone():
            raise ApiError(422, "invalid_reference", f"{field} does not belong to the customer.")


def _next_id(conn) -> str:
    n = conn.execute("SELECT coalesce(max(CAST(substr(id,5) AS INTEGER)),0) FROM complaints "
                     "WHERE id GLOB 'POC-[0-9]*'").fetchone()[0]
    return f"POC-{n + 1:04d}"


# PUBLIC_INTERFACE
def create(conn, p: dict, user: dict) -> dict:
    """Validate and save a complaint with repeat evidence, events and audit in ONE transaction."""
    cfg = get_config()
    _validate(conn, p, cfg)
    session = sessions_svc.get_open(conn, p["session_id"], user) if p.get("session_id") else None
    if p.get("repeat_input_hash"):
        cur = repeat_svc.input_hash(cfg["repeat_rule"], p)
        if cur != p["repeat_input_hash"]:
            raise ApiError(409, "stale_repeat_check", "Repeat check is out of date; run it again.")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cid, stamp = _next_id(conn), db.reference_now().isoformat()
        result = repeat_svc.evaluate_repeat(cfg["repeat_rule"], p, load_history(conn, p["customer_id"]),
                                            db.reference_now(), causes_by_id(cfg))
        payload = {"description": p["description"], "synthetic": True, "complaint_type": p["complaint_type"],
                   "other_reason": p.get("other_reason") or ""}
        conn.execute(
            "INSERT INTO complaints(id,customer_id,site_id,contract_id,order_id,root_cause,created,status,"
            "session_id,payload,channel,registration_date,registering_user,original_text,language,summary_json,"
            "summary_meta,complaint_type,other_reason,rule_version,taxonomy_version,repeat_detected,scenario,"
            "is_poc,is_seed) VALUES(?,?,?,?,?,?,?,'open',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)",
            (cid, p["customer_id"], p.get("site_id"), p.get("contract_id"), p.get("order_id"), p["root_cause"],
             stamp, p.get("session_id"), json.dumps(payload), p["channel"], stamp, user["id"], p["description"],
             p.get("language"), json.dumps(p.get("summary")), json.dumps(p.get("summary_meta")),
             p["complaint_type"], (p.get("other_reason") or "").strip() or None, cfg["repeat_rule"]["version"],
             cfg["taxonomy_version"], int(result["is_repeat"]), p.get("scenario") or (session or {}).get("scenario")))
        _insert_repeat_check(conn, p.get("session_id"), cid, result)
        if session:
            _record_outcome(conn, session["id"], p)
            conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)",
                         (session["id"], "review_save", "step_completed", db.now()))
            conn.execute("UPDATE sessions SET status='saved',ended=? WHERE id=?", (db.now(), session["id"]))
            audit(conn, user["id"], "session_completed", {"session_id": session["id"], "outcome": "saved"})
        audit(conn, user["id"], "repeat_rule_evaluated", {"complaint_id": cid, "is_repeat": result["is_repeat"],
                                                          "rule_version": result["rule_version"]})
        audit(conn, user["id"], "complaint_saved", {"complaint_id": cid, "root_cause": p["root_cause"]})
        conn.commit()
    except Exception:
        conn.rollback()
        _record_failure(conn, user, session)
        raise ApiError(500, "save_failed", "Complaint could not be saved; nothing was stored. Please retry.")
    return {"id": cid, "repeat": {k: result[k] for k in ("is_repeat", "count", "matches", "rule_version")},
            "poc_only": True}


def _record_outcome(conn, session_id: str, p: dict) -> None:
    """Log suggestion outcome from the SERVER-recorded classify event (not client claims)."""
    row = conn.execute("SELECT candidates FROM ai_events WHERE session_id=? AND operation='classify' "
                       "AND status='ok' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
    shown = [c["root_cause_id"] for c in json.loads(row["candidates"] or "[]")] if row else []
    conn.execute("INSERT INTO ai_events(session_id,operation,candidates,selected,in_top3,status,at) "
                 "VALUES(?,?,?,?,?,?,?)",
                 (session_id, "classification_outcome", json.dumps(shown), p["root_cause"],
                  int(p["root_cause"] in shown) if shown else None, "ok", db.now()))


def _record_failure(conn, user: dict, session) -> None:
    """Best-effort failure trace after rollback (separate transaction)."""
    try:
        if session:
            conn.execute("UPDATE sessions SET failure_status='save_failed' WHERE id=?", (session["id"],))
        audit(conn, user["id"], "complaint_save_failed", {"session_id": session and session["id"]})
        conn.commit()
    except Exception:  # noqa: BLE001 - never mask the original error
        conn.rollback()


def _row(r) -> dict:
    d = dict(r)
    for k in ("payload", "summary_json", "summary_meta"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    d["repeat_detected"] = None if d.get("repeat_detected") is None else bool(d["repeat_detected"])
    return d


# PUBLIC_INTERFACE
def list_complaints(conn, f: dict, page: int, size: int) -> dict:
    """Paginated history with optional filters."""
    where, args = ["1=1"], []
    for col, key in (("customer_id", "customer_id"), ("complaint_type", "complaint_type"),
                     ("root_cause", "root_cause"), ("status", "status")):
        if f.get(key):
            where.append(f"c.{col}=?")
            args.append(f[key])
    if f.get("customer_number"):
        where.append("c.customer_id IN (SELECT id FROM customers WHERE number=?)")
        args.append(f["customer_number"])
    if f.get("date_from"):
        where.append("c.created>=?")
        args.append(f["date_from"])
    if f.get("date_to"):
        where.append("c.created<=?")
        args.append(f["date_to"])
    if f.get("repeat") is not None:
        where.append("c.repeat_detected=?")
        args.append(int(f["repeat"]))
    if f.get("include_seed") is False:
        where.append("c.is_seed=0")
    w = " AND ".join(where)
    total = conn.execute(f"SELECT count(*) FROM complaints c WHERE {w}", args).fetchone()[0]
    rows = conn.execute(f"SELECT c.* FROM complaints c WHERE {w} ORDER BY c.created DESC, c.id DESC LIMIT ? OFFSET ?",
                        args + [size, (page - 1) * size]).fetchall()
    return {"items": [_row(r) for r in rows], "total": total, "page": page, "page_size": size}


# PUBLIC_INTERFACE
def get(conn, complaint_id: str) -> dict:
    """Return one complaint with repeat evidence and disputes."""
    r = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    if not r:
        raise ApiError(404, "complaint_not_found", "Complaint not found.")
    d = _row(r)
    d["repeat_checks"] = [dict(x, matching_ids=json.loads(x["matching_ids"] or "[]"),
                               explanation=json.loads(x["explanation"] or "{}"))
                          for x in conn.execute("SELECT * FROM repeat_checks WHERE complaint_id=? ORDER BY id", (complaint_id,))]
    d["repeat_disputes"] = [dict(x) for x in conn.execute("SELECT * FROM repeat_disputes WHERE complaint_id=?", (complaint_id,))]
    return d
