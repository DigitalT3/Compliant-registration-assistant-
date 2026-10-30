"""The audit trail for administrators: every saved complaint record, and for each one how it was made.

The list shows all saved records (the PoC's own registrations first, then the synthetic history). The detail of one record
holds the record in the target field structure (FR-14), where every field's value came from (prefilled, default, suggested,
typed, edited), the repeat check with the earlier complaints and the decisions on them, and the audit-log events about it.
"""
import json

from . import complaints, field_mapping
from . import sessions as sessions_svc
from .lookup import _like
from ..settings import get_config


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
    flags = log_flags(conn, [dict(r) for r in conn.execute(
        f"SELECT id, is_seed, session_id, scenario FROM complaints WHERE id IN ({','.join('?' * len(items))})", [i['id'] for i in items])]) if items else {}
    for d in items:
        d["log"] = flags.get(d["id"], "n/a")
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
            "origins": origins, "repeat_checks": rec.get("repeat_checks", []), "repeat_disputes": rec.get("repeat_disputes", []), "events": events,
            "log": registration_log(conn, rec)}


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


SAMPLE_PREFIX = "rating-sample-"       # complaints saved by scripts.seed_rating_sample for the process owners to rate: not test registrations


def _no_log_needed(scenario, is_seed) -> bool:
    return bool(is_seed) or (scenario or "").startswith(SAMPLE_PREFIX)


# ---- FR-15: the log of one registration ------------------------------------------------------------------------------

def _missing(mode, status, steps, finals, prefills, ai, tracked) -> list:
    """What the log of a saved registration lacks (empty = complete).

    Needed for every registration: a session that ended saved; every step entered and completed; the origin of all tracked
    fields at save; the fields filled before the employee touched them (prefilled or default). In assistant mode also the
    suggestions shown (an AI call was logged) and the outcome of the cause (accepted or changed).
    """
    bad = []
    if status != "saved":
        bad.append("session_not_saved")
    order = sessions_svc.STEPS
    for i, step in enumerate(order):
        moved_on = i + 1 < len(order) and steps.get((order[i + 1], "step_entered"))      # entering the next step closes this one
        if not steps.get((step, "step_entered")):
            bad.append(f"step_not_entered:{step}")
        elif not steps.get((step, "step_completed")) and not moved_on:
            bad.append(f"step_not_completed:{step}")
    if finals < tracked:
        bad.append(f"field_origins_at_save:{finals}_of_{tracked}")
    if not prefills:
        bad.append("prefill_not_logged")
    if mode == "assistant":
        if not (ai.get("classify") or ai.get("analyze")):
            bad.append("suggestions_not_logged")
        if not ai.get("classification_outcome"):
            bad.append("outcome_not_logged")
    return bad


def _grouped(conn, sql: str, ids: list) -> list:
    return conn.execute(sql.replace("{ids}", ",".join("?" * len(ids))), ids).fetchall()


# PUBLIC_INTERFACE
def log_flags(conn, rows: list) -> dict:
    """``{complaint id: "complete" | "incomplete" | "n/a"}`` for a page of records, with a few queries for the whole page."""
    out = {r["id"]: "n/a" for r in rows}
    wanted = [r for r in rows if not _no_log_needed(r.get("scenario"), r["is_seed"])]
    sids = [r["session_id"] for r in wanted if r["session_id"]]
    for r in wanted:
        if not r["session_id"]:
            out[r["id"]] = "incomplete"
    if not sids:
        return out
    tracked = len(get_config()["metrics"]["tracked_fields"])
    sess = {r["id"]: r for r in _grouped(conn, "SELECT id, mode, status FROM sessions WHERE id IN ({ids})", sids)}
    steps, finals, prefills, ai = {}, {}, {}, {}
    for r in _grouped(conn, "SELECT session_id, step, event_type, count(*) AS n FROM step_events WHERE session_id IN ({ids}) GROUP BY session_id, step, event_type", sids):
        key = sessions_svc.LEGACY_STEPS.get(r["step"], r["step"])
        steps.setdefault(r["session_id"], {})[(key, r["event_type"])] = r["n"]
    for r in _grouped(conn, "SELECT session_id, event_type, changed, count(*) AS n FROM field_events WHERE session_id IN ({ids}) GROUP BY session_id, event_type, changed", sids):
        if r["event_type"] == "final":
            finals[r["session_id"]] = finals.get(r["session_id"], 0) + r["n"]
        elif r["event_type"] == "field" and not r["changed"]:
            prefills[r["session_id"]] = prefills.get(r["session_id"], 0) + r["n"]
    for r in _grouped(conn, "SELECT session_id, operation, count(*) AS n FROM ai_events WHERE session_id IN ({ids}) GROUP BY session_id, operation", sids):
        ai.setdefault(r["session_id"], {})[r["operation"]] = r["n"]
    for r in wanted:
        sid, se = r["session_id"], sess.get(r["session_id"])
        if sid and se:
            bad = _missing(se["mode"], se["status"], steps.get(sid, {}), finals.get(sid, 0), prefills.get(sid, 0), ai.get(sid, {}), tracked)
            out[r["id"]] = "incomplete" if bad else "complete"
        elif sid:
            out[r["id"]] = "incomplete"
    return out


def _time_check(events: list, ended: str | None, started: str, steps_seconds: float) -> dict:
    """Do the times per step add up to the registration's total? Gaps beyond a few seconds must be explained by the idle cap."""
    from datetime import datetime
    cap = get_config()["metrics"].get("step_idle_cap_seconds") or 0
    longest, cur = 0.0, None
    for e in events:
        if e["event_type"] == "step_entered":
            if cur is not None:
                longest = max(longest, (datetime.fromisoformat(e["at"]) - datetime.fromisoformat(cur)).total_seconds())
            cur = e["at"]
    if cur is not None and ended:
        longest = max(longest, (datetime.fromisoformat(ended) - datetime.fromisoformat(cur)).total_seconds())
    total = (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() if ended else None
    if total is None:
        return {"session_seconds": None, "steps_seconds": round(steps_seconds, 1), "result": "open"}
    gap = total - steps_seconds
    result = "consistent" if gap <= 3 else "capped" if cap and longest > cap else "gap"
    return {"session_seconds": round(total, 1), "steps_seconds": round(steps_seconds, 1), "gap": round(gap, 1), "result": result}


def _result_of_cause(selected, shown):
    if not shown:
        return "no_suggestion"
    if selected == shown[0]:
        return "kept_first"
    return "chose_other_of_three" if selected in shown else "chose_outside"


# PUBLIC_INTERFACE
def registration_log(conn, rec: dict) -> dict:
    """Everything logged about one registration: time per step, what was prefilled, the suggestions shown, accepted or changed."""
    if rec.get("is_seed"):
        return {"applicable": False, "reason": "synthetic_history"}
    if _no_log_needed(rec.get("scenario"), False):
        return {"applicable": False, "reason": "rating_sample"}
    sid = rec.get("session_id")
    sess = sid and conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        return {"applicable": True, "complete": False, "missing": ["session"], "steps": [], "fields": {}, "suggestions": None}
    sess = dict(sess)
    events = [dict(r) for r in conn.execute("SELECT step, event_type, at FROM step_events WHERE session_id=? ORDER BY id", (sid,))]
    seconds = sessions_svc.step_durations(events, sess.get("ended"))
    counts = {}
    for e in events:
        key = (sessions_svc.LEGACY_STEPS.get(e["step"], e["step"]), e["event_type"])
        counts[key] = counts.get(key, 0) + 1
    fe = [dict(r) for r in conn.execute("SELECT field, origin, event_type, changed, at FROM field_events WHERE session_id=? ORDER BY id", (sid,))]
    finals = [e for e in fe if e["event_type"] == "final"]
    start = [e for e in fe if e["event_type"] == "field" and not e["changed"]]
    edits = [{"field": e["field"], "origin": e["origin"], "at": e["at"]} for e in fe if e["event_type"] == "field" and e["changed"]]
    ai_rows = [dict(r) for r in conn.execute("SELECT * FROM ai_events WHERE session_id=? ORDER BY id", (sid,))]
    ai_ops = {}
    for r in ai_rows:
        ai_ops[r["operation"]] = ai_ops.get(r["operation"], 0) + 1
    tracked = len(get_config()["metrics"]["tracked_fields"])
    bad = _missing(sess["mode"], sess["status"], counts, len(finals), len(start), ai_ops, tracked)
    tcheck = _time_check(events, sess.get("ended"), sess["started"], sum(seconds.values()))
    if tcheck["result"] == "gap":
        bad.append(f"time_does_not_add_up:{tcheck['gap']}s")

    def last(*ops):
        return next((r for r in reversed(ai_rows) if r["operation"] in ops and r["status"] == "ok"), None)
    cls, summ = last("classify", "analyze"), last("summarise", "analyze")
    causes = json.loads(cls["candidates"] or "[]") if cls else []
    detail = lambda r: json.loads(r["detail"]) if r and r.get("detail") else {}
    outcome = next((r for r in reversed(ai_rows) if r["operation"] == "classification_outcome"), None)
    selected = outcome["selected"] if outcome else rec.get("root_cause")
    suggested = detail(summ).get("summary")
    saved = rec.get("summary_json") or {}
    changed = []
    from_context = set(saved.get("context_extras") or [])            # filled from the chosen order after the model answered, not edited
    if suggested is not None:
        for k in ("what", "where", "when", "impact"):
            if (suggested.get(k) or "").strip() != (saved.get(k) or "").strip():
                changed.append(k)
        for k in sorted((set(suggested.get("extras") or {}) | set(saved.get("extras") or {})) - from_context):
            if ((suggested.get("extras") or {}).get(k) or "").strip() != ((saved.get("extras") or {}).get(k) or "").strip():
                changed.append(k)
    origins = {}
    for e in finals:
        origins[e["origin"]] = origins.get(e["origin"], 0) + 1
    return {
        "applicable": True, "complete": not bad, "missing": bad, "mode": sess["mode"], "participant": sess.get("participant_id"),
        "scenario": sess.get("scenario"), "started": sess["started"], "ended": sess.get("ended"), "status": sess["status"],
        "steps": [{"step": st, "seconds": seconds.get(st, 0), "visits": counts.get((st, "step_entered"), 0)} for st in sessions_svc.STEPS],
        "total_seconds": round(sum(seconds.values()), 1), "time_check": tcheck,
        "prefilled_at_start": {o: sum(1 for e in start if e["origin"] == o) for o in ("prefilled", "default")},
        "fields_at_save": origins, "edits": edits,
        "suggestions": {
            "ai_calls": [{"operation": r["operation"], "status": r["status"], "error": r["error_category"], "ms": r["duration_ms"], "model": r["model"]}
                         for r in ai_rows if r["operation"] != "classification_outcome"],
            "complaint_type": detail(cls).get("complaint_type"), "saved_type": rec.get("complaint_type"),
            "type_result": ("no_suggestion" if not detail(cls).get("complaint_type")
                            else "kept" if detail(cls).get("complaint_type") == rec.get("complaint_type") else "changed"),
            "causes": causes, "selected_cause": selected,
            "cause_result": _result_of_cause(selected, [c["root_cause_id"] for c in causes]),
            "in_top3": outcome["in_top3"] if outcome else None,
            "summary_suggested": suggested, "summary_changed_fields": changed if suggested is not None else None,
            "summary_result": None if suggested is None else ("changed" if changed else "kept")},
    }


# PUBLIC_INTERFACE
def unsaved(conn, page: int, size: int) -> dict:
    """Registrations that were started but not saved (abandoned, failed or still open), with what was logged up to where they stopped."""
    sessions_svc.sweep_abandoned(conn)
    where = "s.status<>'saved' AND s.id NOT IN (SELECT session_id FROM complaints WHERE session_id IS NOT NULL)"
    total = conn.execute(f"SELECT count(*) FROM sessions s WHERE {where}").fetchone()[0]
    rows = conn.execute(
        "SELECT s.id, s.actor, s.mode, s.participant_id, s.scenario, s.started, s.ended, s.status, s.failure_status, u.name AS actor_name "
        f"FROM sessions s LEFT JOIN users u ON u.id=s.actor WHERE {where} ORDER BY s.started DESC, s.id DESC LIMIT ? OFFSET ?",
        (size, (page - 1) * size)).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        events = [dict(e) for e in conn.execute("SELECT step, event_type, at FROM step_events WHERE session_id=? ORDER BY id", (d["id"],))]
        seconds = sessions_svc.step_durations(events, d["ended"])
        reached = [sessions_svc.LEGACY_STEPS.get(e["step"], e["step"]) for e in events if e["event_type"] == "step_entered"]
        d["last_step"] = reached[-1] if reached else None
        d["steps"] = [{"step": st, "seconds": seconds.get(st, 0)} for st in sessions_svc.STEPS]
        d["total_seconds"] = round(sum(seconds.values()), 1)
        d["fields_logged"] = conn.execute("SELECT count(*) FROM field_events WHERE session_id=?", (d["id"],)).fetchone()[0]
        d["ai_calls"] = conn.execute("SELECT count(*) FROM ai_events WHERE session_id=?", (d["id"],)).fetchone()[0]
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": size}
