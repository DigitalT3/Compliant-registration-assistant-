"""Sign-off of the repeat rule by its owner (Juul at Renewi).

Same idea as the cause-list agreement: a sign-off counts for one exact version of the rule parameters. When the rule
is edited, earlier sign-offs stay as history but no longer count, so "signed off" always means the rule on screen.
Records live in ``app_settings`` and every one is written to the audit log.
"""
import hashlib
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config

KEY = "repeat_rule_signoff"
PARAMS = ("enabled", "lookback_days", "match_keys", "cause_mode", "eligible_statuses", "missing_values")


# PUBLIC_INTERFACE
def content_hash(cfg: dict | None = None) -> str:
    """Short fingerprint of the rule parameters (not the version label or edit time)."""
    rule = (cfg or get_config())["repeat_rule"]
    blob = json.dumps({k: rule.get(k) for k in PARAMS}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _load(conn) -> list:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (KEY,)).fetchone()
    return json.loads(row[0]) if row else []


# PUBLIC_INTERFACE
def status(conn, cfg: dict | None = None) -> dict:
    """``draft``, ``changes_requested`` or ``signed_off`` for the rule as it is now."""
    cfg = cfg or get_config()
    here, required = content_hash(cfg), int(cfg.get("rule_signoff", {}).get("required", 1))
    latest: dict = {}
    for r in _load(conn):
        latest[r["user_id"]] = r
    now = [r for r in latest.values() if r["content_hash"] == here]
    signed = [r for r in now if r["decision"] == "sign_off"]
    state = "changes_requested" if any(r["decision"] == "changes" for r in now) else "signed_off" if len(signed) >= required else "draft"
    reviews = sorted(({"user_id": r["user_id"], "name": r["name"], "decision": r["decision"], "comment": r.get("comment"),
                       "at": r["at"], "current": r["content_hash"] == here, "rule_version": r.get("rule_version")}
                      for r in latest.values()), key=lambda r: r["at"], reverse=True)
    return {"state": state, "required": required, "signed": len(signed), "content_hash": here,
            "rule_version": cfg["repeat_rule"].get("version"), "reviews": reviews,
            "signed_by": [r["name"] for r in signed] if state == "signed_off" else [],
            "signed_at": max(r["at"] for r in signed) if state == "signed_off" else None}


# PUBLIC_INTERFACE
def review(conn, user: dict, decision: str, comment: str | None) -> dict:
    """Record the caller's decision on the rule as it is now (replaces their earlier one)."""
    if decision not in ("sign_off", "changes"):
        raise ApiError(422, "invalid_decision", "decision must be 'sign_off' or 'changes'.")
    comment = (comment or "").strip()
    if decision == "changes" and not comment:
        raise ApiError(422, "comment_required", "Say what should change.")
    cfg = get_config()
    entry = {"user_id": user["id"], "name": user["name"], "decision": decision, "comment": comment[:500] or None,
             "at": db.now(), "content_hash": content_hash(cfg), "rule_version": cfg["repeat_rule"].get("version")}
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (KEY, json.dumps(_load(conn) + [entry], ensure_ascii=False)))
    audit(conn, user["id"], "repeat_rule_signed_off" if decision == "sign_off" else "repeat_rule_changes_requested",
          {"content_hash": entry["content_hash"], "rule_version": entry["rule_version"], "comment": entry["comment"]})
    conn.commit()
    return status(conn, cfg)
