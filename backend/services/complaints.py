"""Complaint validation and ATOMIC persistence to the PoC database only (FR-14, FR-16).

Nothing here talks to any external system: there is no live-system write path.
"""
import json
import logging
from datetime import date

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import causes_by_id, get_config
from . import accounts as accounts_svc
from . import disputes as disputes_svc
from . import field_mapping as field_mapping_svc
from . import prefill as prefill_svc
from . import repeat as repeat_svc
from . import sessions as sessions_svc

log = logging.getLogger(__name__)


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


# PUBLIC_INTERFACE
def valid_other_reason(reason) -> bool:
    """A reason for the cause "Other": at least 3 characters after trimming, and not only punctuation ("." is not a reason)."""
    text = (reason or "").strip()
    return len(text) >= 3 and any(ch.isalnum() for ch in text)


def _validate(conn, p: dict, cfg: dict) -> None:
    missing = [f for f in cfg["required_fields"] if not str(p.get(f) or "").strip()]
    if missing:
        raise ApiError(422, "missing_required_fields", "Required fields missing.", {"fields": missing})
    if p["complaint_type"] not in {t["id"] for t in cfg["types"]}:
        raise ApiError(422, "invalid_type", "Unknown complaint type.")
    if p["root_cause"] not in {c["id"] for c in cfg["root_causes"]}:
        raise ApiError(422, "invalid_root_cause", "Root cause is not in the active taxonomy.")
    if p["root_cause"] == "other" and not valid_other_reason(p.get("other_reason")):
        raise ApiError(422, "other_reason_required", "A reason is required when 'Other' is selected: at least 3 characters, with letters or digits.")
    if not conn.execute("SELECT 1 FROM customers WHERE id=?", (p["customer_id"],)).fetchone():
        raise ApiError(422, "invalid_customer", "Unknown customer.")
    for field, table in (("site_id", "sites"), ("contract_id", "contracts"), ("order_id", "orders")):
        if p.get(field) and not conn.execute(f"SELECT 1 FROM {table} WHERE id=? AND customer_id=?",
                                             (p[field], p["customer_id"])).fetchone():
            raise ApiError(422, "invalid_reference", f"{field} does not belong to the customer.")


def _registration(conn, p: dict, user: dict) -> tuple[str, str]:
    """Registering user and registration date: the employee's own and today's unless the form changed them."""
    who = (p.get("registering_user") or "").strip() or user["id"]
    if who != user["id"]:
        ok = {c["id"] for c in accounts_svc.colleagues(conn)}
        if who not in ok:
            raise ApiError(422, "invalid_registering_user", "The registering user must be an active colleague who can register complaints.")
    day = (p.get("registration_date") or "").strip() or prefill_svc.today()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise ApiError(422, "invalid_registration_date", "The registration date must be a date like 2026-10-30.")
    now = date.fromisoformat(prefill_svc.today())
    if d > now or (now - d).days > 366:
        raise ApiError(422, "invalid_registration_date", "The registration date cannot be in the future or more than a year back.")
    return who, d.isoformat()


def _decisions(conn, p: dict, cfg: dict) -> list:
    """The employee's confirm/dispute decisions, checked against the earlier complaints the rule links right now."""
    raw = p.get("repeat_decisions") or []
    if not raw:
        return []
    found = {m["id"] for m in repeat_svc.evaluate_repeat(cfg["repeat_rule"], p, load_history(conn, p["customer_id"]),
                                                          db.reference_now(), causes_by_id(cfg))["matches"]}
    out, seen = [], set()
    for d in raw:
        prior = d["prior_complaint_id"]
        if prior not in found or prior in seen:
            raise ApiError(422, "invalid_repeat_decision", f"{prior} is not an earlier complaint the rule links to this one (or is listed twice).")
        seen.add(prior)
        out.append((prior, d["decision"], disputes_svc.clean(d["decision"], d.get("reason"))))
    return out


def _form_fields(conn, p: dict, cfg: dict) -> dict:
    """Resolve the defaulted form fields server-side: explicit value, else the type default.

    The container is always read from the selected order, never taken from the client.
    """
    defaults = {**cfg["defaults"].get("_all", {}), **cfg["defaults"].get(p["complaint_type"], {})}
    options = cfg.get("field_options", {})
    out = {}
    for name in ("priority", "owner_team"):
        value = (p.get(name) or defaults.get(name) or "").strip()
        if value and name in options and value not in options[name]:
            raise ApiError(422, "invalid_" + name, f"{name} must be one of {options[name]}.")
        out[name] = value or None
    days = defaults.get("response_target_days")
    out["response_target_days"] = int(days) if days not in (None, "") else None
    out["status"] = defaults.get("status", "open")
    order = p.get("order_id") and conn.execute("SELECT container FROM orders WHERE id=?", (p["order_id"],)).fetchone()
    out["container"] = order["container"] if order else None
    return out


def _record_final_provenance(conn, session, p: dict, cfg: dict) -> None:
    """Store the origin of each tracked field as it was saved (basis of the prefill rate, FR-15)."""
    if not session or not p.get("field_provenance"):
        return
    tracked = cfg["metrics"]["tracked_fields"]
    for name in tracked:
        origin = p["field_provenance"].get(name, "blank")
        if origin not in sessions_svc.ORIGINS:
            origin = "blank"
        conn.execute("INSERT INTO field_events(session_id,field,origin,event_type,changed,at) VALUES(?,?,?,?,0,?)",
                     (session["id"], name, origin, "final", db.now()))


def _next_id(conn) -> str:
    n = conn.execute("SELECT coalesce(max(CAST(substr(id,5) AS INTEGER)),0) FROM complaints "
                     "WHERE id GLOB 'COM-[0-9]*'").fetchone()[0]
    return f"COM-{n + 1:04d}"


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
    extra = _form_fields(conn, p, cfg)   # validates priority/owner_team before any write
    who, reg_day = _registration(conn, p, user)
    decisions = _decisions(conn, p, cfg)                  # refused before anything is written
    try:
        conn.execute("BEGIN IMMEDIATE")
        cid, stamp = _next_id(conn), db.reference_now().isoformat()
        result = repeat_svc.evaluate_repeat(cfg["repeat_rule"], p, load_history(conn, p["customer_id"]),
                                            db.reference_now(), causes_by_id(cfg))
        other_reason = (p.get("other_reason") or "").strip() if p["root_cause"] == "other" else ""     # a reason only belongs to "Other"
        payload = {"description": p["description"], "synthetic": True, "complaint_type": p["complaint_type"],
                   "other_reason": other_reason}
        row = {
            "id": cid, "customer_id": p["customer_id"], "site_id": p.get("site_id"),
            "contract_id": p.get("contract_id"), "order_id": p.get("order_id"), "root_cause": p["root_cause"],
            "created": stamp, "status": extra["status"], "session_id": p.get("session_id"),
            "payload": json.dumps(payload), "channel": p["channel"], "registration_date": reg_day,
            "registering_user": who, "creator_role": user.get("role"), "original_text": p["description"], "language": p.get("language"),
            "summary_json": json.dumps(p.get("summary")), "summary_meta": json.dumps(p.get("summary_meta")),
            "complaint_type": p["complaint_type"], "other_reason": other_reason or None,
            "rule_version": cfg["repeat_rule"]["version"], "taxonomy_version": cfg["taxonomy_version"],
            "repeat_detected": int(result["is_repeat"]),
            "scenario": p.get("scenario") or (session or {}).get("scenario"), "is_poc": 1, "is_seed": 0,
            "priority": extra["priority"], "owner_team": extra["owner_team"],
            "response_target_days": extra["response_target_days"], "container": extra["container"],
            "root_cause_category": causes_by_id(cfg)[p["root_cause"]]["level1"],
        }
        absent = field_mapping_svc.missing_required(field_mapping_svc.to_target(row))     # FR-14: the record must fill every required target field
        if absent:
            raise RuntimeError(f"record would miss required target fields: {absent}")
        with db.pipeline(conn):                                     # the writes travel together: one round trip, not one per row
            conn.execute(f"INSERT INTO complaints({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
            _record_final_provenance(conn, session, p, cfg)
            _insert_repeat_check(conn, p.get("session_id"), cid, result)
            for prior, decision, reason in decisions:                   # stored in the same transaction as the complaint
                disputes_svc.insert(conn, user["id"], cid, prior, decision, reason)
            if session:
                _record_outcome(conn, session["id"], p)
                conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)",
                             (session["id"], "repeat_save", "step_completed", db.now()))
                conn.execute("UPDATE sessions SET status='saved',ended=? WHERE id=?", (db.now(), session["id"]))
                audit(conn, user["id"], "session_completed", {"session_id": session["id"], "outcome": "saved"})
            audit(conn, user["id"], "repeat_rule_evaluated", {"complaint_id": cid, "is_repeat": result["is_repeat"],
                                                              "rule_version": result["rule_version"]})
            audit(conn, user["id"], "complaint_saved", {"complaint_id": cid, "root_cause": p["root_cause"],
                                                               **({"registered_for": who} if who != user["id"] else {})})
        conn.commit()
    except Exception:
        log.exception("complaint save failed")   # the API response stays generic; the cause goes to the server log
        conn.rollback()
        _record_failure(conn, user, session)
        raise ApiError(500, "save_failed", "Complaint could not be saved; nothing was stored. Please retry.")
    return {"id": cid, "repeat": {k: result[k] for k in ("is_repeat", "count", "matches", "rule_version")},
            "poc_only": True}


def _record_outcome(conn, session_id: str, p: dict) -> None:
    """Log suggestion outcome from the SERVER-recorded classify event (not client claims)."""
    row = conn.execute("SELECT candidates FROM ai_events WHERE session_id=? AND operation IN ('classify','analyze') "
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
