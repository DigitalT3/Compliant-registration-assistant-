"""Dashboard metrics computed ONLY from recorded data, each with its sample size (FR-15, FR-17).

Definitions: duration = wall-clock seconds from server session start to save
(includes idle time within the session; sessions idle past the abandon limit are
'abandoned' and excluded from the duration metric). Baseline comparison is
reported only when ``baseline.current_process_seconds`` is configured.
"""
import json
import statistics
from collections import Counter

from .. import db
from ..settings import get_config
from . import sessions as sessions_svc

DEFINITIONS = {
    "duration": "Server-recorded seconds from session start to save, saved sessions only; includes idle time.",
    "top_three_rate": "Share of saved complaints whose final cause was among AI candidates shown (n = sessions with candidates).",
    "prefill_rate": "Fields prefilled or defaulted / tracked form fields, taken from each saved registration's final field origins.",
    "synthetic": "Includes only PoC-recorded sessions; seeded history has no sessions.",
}


def _rate(num, den):
    return {"value": round(num / den, 4) if den else None, "n": den}


def _where(f: dict):
    w, a = ["1=1"], []
    if f.get("date_from"):
        w.append("s.started>=?"); a.append(f["date_from"])
    if f.get("date_to"):
        w.append("s.started<=?"); a.append(f["date_to"])
    for col, key in (("c.complaint_type", "complaint_type"), ("c.root_cause", "root_cause"),
                     ("s.scenario", "scenario"), ("s.user_group", "group"), ("s.mode", "mode"),
                     ("s.participant_id", "participant")):
        if f.get(key):
            w.append(f"{col}=?"); a.append(f[key])
    if f.get("repeat") is not None:
        w.append("c.repeat_detected=?"); a.append(int(f["repeat"]))
    return " AND ".join(w), a


def _rows(conn, f):
    w, a = _where(f)
    return [dict(r) for r in conn.execute(
        "SELECT s.id,s.actor,s.started,s.ended,s.status,s.scenario,s.user_group,s.failure_status,s.mode,s.participant_id,"
        "c.id complaint_id,c.root_cause,c.complaint_type,c.repeat_detected,c.other_reason "
        f"FROM sessions s LEFT JOIN complaints c ON c.session_id=s.id WHERE {w} ORDER BY s.started DESC", a)]


def _duration(r) -> float | None:
    if r["status"] != "saved" or not r["ended"]:
        return None
    from datetime import datetime
    return (datetime.fromisoformat(r["ended"]) - datetime.fromisoformat(r["started"])).total_seconds()


# PUBLIC_INTERFACE
def summary(conn, f: dict) -> dict:
    """Aggregate metrics with sample sizes and empty-state flag."""
    sessions_svc.sweep_abandoned(conn)
    rows = _rows(conn, f)
    ids = [r["id"] for r in rows]
    out = {"definitions": DEFINITIONS, "synthetic": True, "filters": {k: v for k, v in f.items() if v is not None},
           "empty": not rows, "sessions": {"started": len(rows)}}
    if not rows:
        return out
    ph = ",".join("?" * len(ids))
    saved = [r for r in rows if r["status"] == "saved"]
    cnt = Counter(r["status"] for r in rows)
    out["sessions"].update({"saved": cnt["saved"], "abandoned": cnt["abandoned"], "failed": cnt["failed"],
                            "active": cnt["active"], "save_rate": _rate(cnt["saved"], len(rows))})
    durs = [d for d in map(_duration, rows) if d is not None]
    base, base_n, base_src = _baseline(conn, f)
    avg = statistics.mean(durs) if durs else None
    out["duration_seconds"] = {"n": len(durs), "mean": avg and round(avg, 2),
                               "median": durs and round(statistics.median(durs), 2) or None,
                               "baseline_seconds": base, "baseline_n": base_n, "baseline_source": base_src,
                               "vs_baseline_seconds": (round(avg - base, 2) if base and avg is not None else None),
                               "faster_than_baseline": (round(1 - avg / base, 4) if base and avg is not None else None),
                               "baseline_note": get_config()["baseline"]["note"] if not base else None}
    steps: dict = {}
    for r in rows:
        ev = [dict(e) for e in conn.execute("SELECT step,event_type,at FROM step_events WHERE session_id=? ORDER BY id", (r["id"],))]
        for k, v in sessions_svc.step_durations(ev, r["ended"]).items():
            steps.setdefault(k, []).append(v)
    out["step_seconds"] = {k: {"mean": round(statistics.mean(v), 2), "n": len(v)} for k, v in steps.items()}
    fe = Counter(r[0] for r in conn.execute(
        f"SELECT origin FROM field_events WHERE event_type='field' AND session_id IN ({ph})", ids))
    final = Counter(r[0] for r in conn.execute(
        f"SELECT origin FROM field_events WHERE event_type='final' AND session_id IN ({ph})", ids))
    system_filled = sum(final[o] for o in get_config()["metrics"]["prefill_origins"])
    out["fields"] = {"prefill_rate": _rate(system_filled, sum(final.values())), "final_origins": dict(final),
                     "origins": dict(fe),
                     "edited_after_prefill": _rate(fe["edited"], fe["prefilled"] + fe["edited"])}
    oc = [r for r in conn.execute(f"SELECT in_top3 FROM ai_events WHERE operation='classification_outcome' "
                                  f"AND in_top3 IS NOT NULL AND session_id IN ({ph})", ids)]
    out["classification"] = {"top_three_rate": _rate(sum(r[0] for r in oc), len(oc)),
                             "other_share": _rate(sum(r["root_cause"] == "other" for r in saved), len(saved)),
                             "by_root_cause": dict(Counter(r["root_cause"] for r in saved)),
                             "other_reasons": [r["other_reason"] for r in saved if r["root_cause"] == "other" and r["other_reason"]]}
    ai = Counter(r[0] for r in conn.execute(f"SELECT status FROM ai_events WHERE operation IN "
                                            f"('summarise','classify','extract','analyze') AND session_id IN ({ph})", ids))
    out["ai"] = {"success_rate": _rate(ai["ok"], ai["ok"] + ai["failed"]), "mock_note": "Rates reflect the provider in use; MOCK is not a real model."}
    out["repeat"] = {"rate": _rate(sum(bool(r["repeat_detected"]) for r in saved), len(saved))}
    if f.get("group_by") in GROUP_KEYS:
        key = GROUP_KEYS[f["group_by"]]
        groups: dict = {}
        for r in rows:
            g = groups.setdefault(r[key] or "none", {"n": 0, "saved": 0, "durs": [], "other": 0, "repeat": 0})
            g["n"] += 1; g["saved"] += r["status"] == "saved"
            g["other"] += r["status"] == "saved" and r["root_cause"] == "other"
            g["repeat"] += r["status"] == "saved" and bool(r["repeat_detected"])
            d = _duration(r)
            if d is not None:
                g["durs"].append(d)
        out["groups"] = {k: {"sessions": g["n"], "saved": g["saved"],
                             "mean_duration": g["durs"] and round(statistics.mean(g["durs"]), 2) or None,
                             "n_duration": len(g["durs"]), "other_share": _rate(g["other"], g["saved"]),
                             "repeat_rate": _rate(g["repeat"], g["saved"])} for k, g in groups.items()}
    out["targets"] = targets(conn, out)
    return out


GROUP_KEYS = {"group": "user_group", "scenario": "scenario", "mode": "mode", "participant": "participant_id"}


def _baseline(conn, f: dict):
    """Mean seconds on today's form: stopwatch rows (filtered by group/scenario) else the config value."""
    w, a = ["1=1"], []
    for col, key in (("user_group", "group"), ("scenario", "scenario")):
        if f.get(key):
            w.append(f"{col}=?"); a.append(f[key])
    rows = [r[0] for r in conn.execute(f"SELECT seconds FROM baseline WHERE {' AND '.join(w)}", a)]
    if rows:
        return round(statistics.mean(rows), 2), len(rows), "stopwatch sessions on today's form"
    cfg_base = get_config()["baseline"].get("current_process_seconds")
    return cfg_base, (1 if cfg_base else 0), ("config.json" if cfg_base else None)


def _status(value, ok):
    return "no_data" if value is None else ("met" if ok else "not_met")


# PUBLIC_INTERFACE
def targets(conn, out: dict) -> list:
    """PRD section 4.3 targets evaluated on the recorded data, each with its sample size.

    ``indicative`` is true when n is below ``targets.small_sample_below``: do not read a verdict into it.
    """
    t, small = get_config()["targets"], get_config()["targets"]["small_sample_below"]
    d = out["duration_seconds"]
    time_ok = d["mean"] is not None and (d["mean"] < t["registration_seconds"] or
                                         (d["faster_than_baseline"] or 0) >= t["faster_than_baseline"])
    other, top3, pre = out["classification"]["other_share"], out["classification"]["top_three_rate"], out["fields"]["prefill_rate"]
    ev = [dict(r) for r in conn.execute(
        "SELECT e.usable, e.expert_cause, c.root_cause FROM evaluations e JOIN complaints c ON c.id=e.complaint_id")]
    usable = [r["usable"] for r in ev]
    labelled = [r for r in ev if r["expert_cause"]]
    daily = [r[0] for r in conn.execute("SELECT would_use_daily FROM exit_interviews")]
    rows = [
        ("time", f"< {t['registration_seconds']} s or >= {int(t['faster_than_baseline'] * 100)}% faster than baseline",
         d["mean"], d["n"], time_ok),
        ("other_share", f"< {int(t['other_share_max'] * 100)}% 'Other'", other["value"], other["n"],
         other["value"] is not None and other["value"] < t["other_share_max"]),
        ("top3", f">= {int(t['top3_acceptance_min'] * 100)}% accepted within top 3", top3["value"], top3["n"],
         top3["value"] is not None and top3["value"] >= t["top3_acceptance_min"]),
        ("prefill", f">= {int(t['prefill_rate_min'] * 100)}% fields prefilled or defaulted", pre["value"], pre["n"],
         pre["value"] is not None and pre["value"] >= t["prefill_rate_min"]),
        ("summary_usable", f">= {int(t['summary_usable_min'] * 100)}% summaries rated usable",
         round(sum(usable) / len(usable), 3) if usable else None, len(usable),
         bool(usable) and sum(usable) / len(usable) >= t["summary_usable_min"]),
        ("cause_accuracy", f">= {int(t['cause_accuracy_min'] * 100)}% agreement with expert labels",
         round(sum(r["expert_cause"] == r["root_cause"] for r in labelled) / len(labelled), 3) if labelled else None,
         len(labelled), bool(labelled) and sum(r["expert_cause"] == r["root_cause"] for r in labelled) / len(labelled) >= t["cause_accuracy_min"]),
        ("daily_use", f">= {t['would_use_daily_min']} testers would use it daily", sum(daily) if daily else None,
         len(daily), sum(daily) >= t["would_use_daily_min"]),
    ]
    return [{"id": i, "target": label, "value": v, "n": n, "status": _status(v, ok), "indicative": 0 < n < small}
            for i, label, v, n, ok in rows]


# PUBLIC_INTERFACE
def session_list(conn, f: dict, page: int, size: int) -> dict:
    """Paginated per-session records with derived durations."""
    sessions_svc.sweep_abandoned(conn)
    rows = _rows(conn, f)
    items = []
    for r in rows[(page - 1) * size: page * size]:
        ev = [dict(e) for e in conn.execute("SELECT step,event_type,at FROM step_events WHERE session_id=? ORDER BY id", (r["id"],))]
        items.append({**r, "duration_seconds": _duration(r), "step_seconds": sessions_svc.step_durations(ev, r["ended"])})
    return {"items": items, "total": len(rows), "page": page, "page_size": size}
