"""Agreeing the root-cause list ("agree v1"): the process owners review the draft, agree or ask for changes.

A review counts for one exact version of the list. The version is a fingerprint of the causes (id, names,
definition, examples, categories); when the list changes, earlier reviews are kept as history but no longer count,
so a list is only "agreed" when enough people agreed to what is on screen now. Reviews live in ``app_settings``
and every one is written to the audit log.
"""
import hashlib
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config

KEY = "taxonomy_review"
DECISIONS = {"agree", "changes"}


# PUBLIC_INTERFACE
def content_hash(cfg: dict | None = None) -> str:
    """Short fingerprint of the cause list as it is now."""
    cfg = cfg or get_config()
    causes = [[c["id"], c.get("level1"), c.get("level2"), c.get("en"), c.get("nl"), c.get("definition"), c.get("examples"), c.get("type")]
              for c in cfg["root_causes"]]
    cats = {c["id"]: [c.get("en"), c.get("nl")] for c in cfg.get("root_cause_categories", [])}
    blob = json.dumps({"causes": causes, "categories": cats}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _load(conn) -> list:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (KEY,)).fetchone()
    return json.loads(row[0]) if row else []


def _save(conn, reviews: list) -> None:
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (KEY, json.dumps(reviews, ensure_ascii=False)))


# PUBLIC_INTERFACE
def status(conn, cfg: dict | None = None) -> dict:
    """The state of the list: ``draft``, ``changes_requested`` or ``agreed`` (needs ``required`` agreements, no open change request)."""
    cfg = cfg or get_config()
    here, required = content_hash(cfg), int(cfg.get("taxonomy_review", {}).get("required_agreements", 3))
    latest: dict = {}
    for r in _load(conn):                                   # one entry per person: their latest review, whatever the version
        latest[r["user_id"]] = r
    now = [r for r in latest.values() if r["content_hash"] == here]
    agreed = [r for r in now if r["decision"] == "agree"]
    open_changes = [r for r in now if r["decision"] == "changes"]
    state = "changes_requested" if open_changes else "agreed" if len(agreed) >= required else "draft"
    reviews = sorted(({"user_id": r["user_id"], "name": r["name"], "decision": r["decision"], "comment": r.get("comment"),
                       "at": r["at"], "current": r["content_hash"] == here} for r in latest.values()), key=lambda r: r["at"], reverse=True)
    return {"state": state, "required": required, "agreed": len(agreed), "content_hash": here,
            "taxonomy_version": cfg["taxonomy_version"], "reviews": reviews,
            "agreed_at": max(r["at"] for r in agreed) if state == "agreed" else None}


# PUBLIC_INTERFACE
def review(conn, user: dict, decision: str, comment: str | None) -> dict:
    """Record the user's review of the list as it is now (replaces their earlier review)."""
    if decision not in DECISIONS:
        raise ApiError(422, "invalid_decision", "decision must be 'agree' or 'changes'.")
    comment = (comment or "").strip()
    if decision == "changes" and not comment:
        raise ApiError(422, "comment_required", "Say what should change.")
    cfg = get_config()
    entry = {"user_id": user["id"], "name": user["name"], "decision": decision, "comment": comment[:500] or None,
             "at": db.now(), "content_hash": content_hash(cfg)}
    _save(conn, _load(conn) + [entry])
    audit(conn, user["id"], "taxonomy_agreed" if decision == "agree" else "taxonomy_changes_requested",
          {"content_hash": entry["content_hash"], "comment": entry["comment"]})
    conn.commit()
    return status(conn, cfg)
