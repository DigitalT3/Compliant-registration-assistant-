"""The audit trail for administrators: every saved complaint record, and for each one how it was made.

The list shows all saved records (the PoC's own registrations first, then the synthetic history). The detail of one record
holds the record in the target field structure (FR-14), where every field's value came from (prefilled, default, suggested,
typed, edited), the repeat check with the earlier complaints and the decisions on them, and the audit-log events about it.
"""
import json

from . import complaints, field_mapping
from .lookup import _like


# PUBLIC_INTERFACE
def records(conn, q: str | None, include_seed: bool, page: int, size: int) -> dict:
    """Paginated list of every saved record: PoC registrations newest first, then the synthetic history."""
    where, args = ["1=1"], []
    if not include_seed:
        where.append("c.is_seed=0")
    if q and q.strip():
        like = _like(q.strip())
        where.append("(lower(c.id) LIKE ? ESCAPE '\\' OR lower(cu.name) LIKE ? ESCAPE '\\' OR cu.number LIKE ?)")
        args += [like, like, q.strip() + "%"]
    w = " AND ".join(where)
    base = ("FROM complaints c LEFT JOIN customers cu ON cu.id=c.customer_id LEFT JOIN sites s ON s.id=c.site_id "
            f"LEFT JOIN users u ON u.id=c.registering_user WHERE {w}")
    total = conn.execute(f"SELECT count(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        "SELECT c.id, c.created, c.registration_date, c.complaint_type, c.root_cause, c.channel, c.status, c.repeat_detected, "
        "c.is_seed, c.is_poc, cu.number AS customer_number, cu.name AS customer_name, s.name AS site_name, u.name AS registered_by "
        f"{base} ORDER BY c.is_seed ASC, c.created DESC, c.id DESC LIMIT ? OFFSET ?", args + [size, (page - 1) * size]).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["repeat_detected"] = None if d["repeat_detected"] is None else bool(d["repeat_detected"])
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": size}


# PUBLIC_INTERFACE
def detail(conn, complaint_id: str) -> dict:
    """One record in the target structure, how each field was filled, the repeat evidence and the audit events about it."""
    rec = complaints.get(conn, complaint_id)                                  # 404 when unknown
    target = field_mapping.to_target(rec)
    origins = []
    if rec.get("session_id"):
        origins = [dict(r) for r in conn.execute(
            "SELECT field, origin FROM field_events WHERE session_id=? AND event_type='final' ORDER BY id", (rec["session_id"],))]
    patterns = [f'%"complaint_id": "{complaint_id}"%'] + ([f'%"session_id": "{rec["session_id"]}"%'] if rec.get("session_id") else [])
    marks = " OR ".join("a.data LIKE ?" for _ in patterns)
    events = [dict(r) for r in conn.execute(
        f"SELECT a.id, a.at, a.action, a.actor, u.name AS actor_name FROM audit a LEFT JOIN users u ON u.id=a.actor WHERE {marks} ORDER BY a.id",
        patterns)]
    return {"id": complaint_id, "is_seed": bool(rec.get("is_seed")), "record": target,
            "missing_required": field_mapping.missing_required(target), "validated": field_mapping.load()["validated"],
            "origins": origins, "repeat_checks": rec.get("repeat_checks", []), "repeat_disputes": rec.get("repeat_disputes", []), "events": events}


# PUBLIC_INTERFACE
def export_rows(conn, include_seed: bool) -> tuple[list, list]:
    """Header (the target field names) and one row per saved record in the target structure."""
    header = [f["target_field"] for f in field_mapping.load()["fields"]]
    sql = "SELECT * FROM complaints" + ("" if include_seed else " WHERE is_seed=0") + " ORDER BY is_seed ASC, created DESC, id DESC"
    rows = []
    for r in conn.execute(sql).fetchall():
        t = field_mapping.to_target(complaints._row(r))
        rows.append([json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in t.values()])
    return header, rows
