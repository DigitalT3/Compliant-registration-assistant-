"""Deterministic, configurable repeat-complaint rule (FR-12). No LLM involvement.

``evaluate_repeat`` is a pure function: rule + candidate + history + clock in,
evidence out. The lookback boundary is INCLUSIVE (exactly N days ago counts).
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _cause_key(code, mode, causes):
    meta = causes.get(code) or {}
    if mode == "level1":
        return meta.get("level1", code)
    return meta.get("level2", code)


# PUBLIC_INTERFACE
def input_hash(rule: dict, candidate: dict) -> str:
    """Hash of the inputs that determine the repeat outcome (used to detect stale checks)."""
    keys = {k: candidate.get(k) for k in rule.get("match_keys", [])}
    keys["root_cause"] = candidate.get("root_cause")
    return hashlib.sha256(json.dumps([rule.get("version"), keys], sort_keys=True).encode()).hexdigest()[:16]


# PUBLIC_INTERFACE
def evaluate_repeat(rule: dict, candidate: dict, history: list, now: datetime, causes: dict | None = None) -> dict:
    """Return ``{is_repeat,count,matches[],rule_version,checked_at,missing_fields,...}``.

    ``history`` rows need: id, customer_id, site_id, root_cause, created, status.
    """
    causes = causes or {}
    mode = rule.get("cause_mode", "level2")
    out = {"is_repeat": False, "count": 0, "matches": [], "missing_fields": [],
           "rule_version": rule.get("version"), "checked_at": now.isoformat(),
           "lookback_days": rule.get("lookback_days"), "input_hash": input_hash(rule, candidate)}
    if not rule.get("enabled", True):
        return {**out, "note": "rule_disabled"}
    keys = list(rule.get("match_keys", []))
    required = keys + (["root_cause"] if mode != "none" else [])
    missing = [k for k in required if not candidate.get(k)]
    if missing:
        out["missing_fields"] = missing
        if rule.get("missing_values", "no_match") == "no_match":
            return {**out, "note": "missing_fields_no_match"}
        keys = [k for k in keys if k not in missing]
    cutoff = now - timedelta(days=rule.get("lookback_days", 0))
    statuses = set(rule.get("eligible_statuses", []))
    matches = []
    for h in history:
        created = _parse(h["created"])
        if not (cutoff <= created <= now) or h["status"] not in statuses:
            continue
        if any(h.get(k) != candidate.get(k) for k in keys):
            continue
        if mode != "none" and "root_cause" not in missing and \
                _cause_key(h["root_cause"], mode, causes) != _cause_key(candidate["root_cause"], mode, causes):
            continue
        reasons = [f"same {k}" for k in keys]
        if mode != "none":
            reasons.append(f"same cause ({mode})")
        days = int((now - created).total_seconds() // 86400)
        reasons += [f"{days} day(s) ago (lookback {rule.get('lookback_days')} inclusive)",
                    f"status {h['status']}"]
        matches.append({"id": h["id"], "date": h["created"], "site_id": h.get("site_id"),
                        "root_cause": h["root_cause"], "status": h["status"], "reason": "; ".join(reasons)})
    matches.sort(key=lambda m: (m["date"], m["id"]), reverse=True)
    return {**out, "is_repeat": bool(matches), "count": len(matches), "matches": matches}
