"""Agreeing the root-cause list ("agree v1"): the process owners review the draft, agree or ask for changes.

A review counts for one exact version of the list. The version is a fingerprint of the causes (id, names,
definition, examples, categories); when the list changes, earlier reviews are kept as history but no longer count,
so a list is only "agreed" when enough people agreed to what is on screen now. Reviews live in ``app_settings``
and every one is written to the audit log.
"""
import hashlib
import json

from ..settings import get_config
from . import agreement

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


# PUBLIC_INTERFACE
def status(conn, cfg: dict | None = None) -> dict:
    """The state of the list: ``draft``, ``changes_requested`` or ``agreed`` (needs ``required`` agreements, no open change request)."""
    cfg = cfg or get_config()
    out = agreement.status(conn, KEY, content_hash(cfg), int(cfg.get("taxonomy_review", {}).get("required_agreements", 3)))
    return {**out, "taxonomy_version": cfg["taxonomy_version"]}


# PUBLIC_INTERFACE
def review(conn, user: dict, decision: str, comment: str | None) -> dict:
    """Record the user's review of the list as it is now (replaces their earlier review)."""
    cfg = get_config()
    agreement.review(conn, user, KEY, content_hash(cfg), decision, comment, ("taxonomy_agreed", "taxonomy_changes_requested"))
    return status(conn, cfg)
