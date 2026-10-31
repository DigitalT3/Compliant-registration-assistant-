"""Health and configuration endpoints."""
import copy
import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db
from ..auth import require
from ..dbutil import audit, connection
from ..errors import ApiError
from ..services import rule_signoff, taxonomy_review
from ..settings import ai_settings, get_config, invalidate_config

router = APIRouter()


class RepeatRuleUpdate(BaseModel):
    """Editable repeat-rule parameters (provisional business rule)."""
    enabled: bool = True
    lookback_days: int = Field(..., ge=0, le=3650, description="Inclusive lookback window in days")
    match_keys: list[str] = Field(..., description="Subset of customer_id, site_id")
    cause_mode: str = Field(..., description="level1, level2 or none")
    eligible_statuses: list[str] = Field(..., min_length=1)
    missing_values: str = Field("no_match", description="no_match or ignore")


class DefaultsUpdate(BaseModel):
    """Channel defaults per complaint type."""
    defaults: dict[str, dict[str, str]]


def _powerbi_report_url() -> str:
    """The saved Power BI report the Dashboard opens (POWERBI_REPORT_URL in .env); only an https link is passed on."""
    url = os.environ.get("POWERBI_REPORT_URL", "").strip()
    return url if url.startswith("https://") else ""


def _public(cfg: dict) -> dict:
    ai = ai_settings()
    return {"app": cfg["app"], "version": cfg["version"], "default_language": cfg["default_language"],
            "taxonomy_version": cfg["taxonomy_version"], "types": cfg["types"], "required_fields": cfg["required_fields"],
            "classification": cfg["classification"], "summary": cfg["summary"], "repeat_rule": cfg["repeat_rule"],
            "defaults": cfg["defaults"], "field_options": cfg["field_options"], "baseline": cfg["baseline"], "provisional_meta": cfg["provisional_meta"],
            "roles": cfg["roles"], "demo_users": cfg["demo_users"], "synthetic_only": True,
            "ui": cfg.get("ui", {}), "functions": cfg["auth"]["functions"], "step_idle_cap_seconds": cfg["metrics"].get("step_idle_cap_seconds"), "step_targets_seconds": cfg["metrics"].get("step_targets_seconds", {}),
            "ai": {"provider": ai["provider"], "model": ai["model"], "mock": ai["provider"] == "mock"},
            "powerbi_report_url": _powerbi_report_url()}


@router.get("/health", tags=["health"], summary="Liveness and mode information")
def health():
    """Return service status and mode flags (synthetic data, AI provider)."""
    return {"status": "ok", "poc": True, "synthetic_only": True, "ai_provider": ai_settings()["provider"],
            "ai_mock": ai_settings()["provider"] == "mock", "ai_region": ai_settings()["region"] or None, "clock_mode": "fixed" if db.reference_now() == db.seed_anchor() else "real"}


@router.get("/api/config", tags=["config"], summary="Effective non-secret configuration")
def get_cfg():
    """Return the effective configuration (no secrets)."""
    with connection() as conn:
        review = taxonomy_review.status(conn)
        signoff = rule_signoff.status(conn)
    return {**_public(get_config()), "taxonomy_review": {k: review[k] for k in ("state", "required", "agreed")},
            "rule_signoff": {k: signoff[k] for k in ("state", "required", "signed", "signed_by", "signed_at", "rule_version")}}


@router.get("/api/config/defaults", tags=["config"], summary="Configured field defaults")
def get_defaults():
    """Return channel defaults per complaint type."""
    c = get_config()
    return {"defaults": c["defaults"], "meta": c["provisional_meta"]["defaults"]}


@router.get("/api/config/root-causes", tags=["config"], summary="Active taxonomy")
def get_causes():
    """Return the active (provisional) taxonomy and complaint types."""
    c = get_config()
    with connection() as conn:
        review = taxonomy_review.status(conn, c)
    return {"taxonomy_version": c["taxonomy_version"], "types": c["types"], "root_causes": c["root_causes"],
            "categories": c["root_cause_categories"], "retired_causes": c.get("retired_causes", []), "meta": c["provisional_meta"]["taxonomy"], "review": review}


class ReviewIn(BaseModel):
    """A process owner's review of the cause list as it is now."""
    decision: str = Field(..., pattern="^(agree|changes)$")
    comment: str | None = Field(None, max_length=500)


@router.post("/api/config/root-causes/review", tags=["config"], summary="Agree to the cause list, or ask for changes")
def review_causes(body: ReviewIn, user: dict = Depends(require("review_taxonomy"))):
    """Record the caller's review. Needs the ``review_taxonomy`` permission (the process owners, role evaluator)."""
    with connection() as conn:
        return taxonomy_review.review(conn, user, body.decision, body.comment)


@router.get("/api/config/repeat-rule", tags=["config"], summary="Active repeat rule")
def get_rule():
    """Return the active repeat rule with provisional metadata and its sign-off status."""
    c = get_config()
    with connection() as conn:
        signoff = rule_signoff.status(conn, c)
    return {"repeat_rule": c["repeat_rule"], "signoff": signoff, "meta": {k: v for k, v in c["provisional_meta"].items() if k.startswith("repeat_rule")}}


def _override(conn, kind: str, content: dict, user: dict, before: dict) -> dict:
    n = conn.execute("SELECT count(*) FROM config_versions WHERE version LIKE 'override-%'").fetchone()[0] + 1
    if "version" in content:
        content["version"] = f"{before['version'].split('-edit-')[0]}-edit-{n}"
    conn.execute("UPDATE config_versions SET active=0 WHERE kind=? AND version LIKE 'override-%'", (kind,))
    conn.execute("INSERT INTO config_versions(kind,version,content,activated_at,active) VALUES(?,?,?,?,1)",
                 (kind, f"override-{n}", json.dumps(content, sort_keys=True), db.now()))
    audit(conn, user["id"], "configuration_changed", {"kind": kind, "before": before, "after": content})
    conn.commit()
    invalidate_config()
    return content


class SignoffIn(BaseModel):
    """The rule owner's decision on the repeat rule as it is now."""
    decision: str = Field(..., pattern="^(sign_off|changes)$")
    comment: str | None = Field(None, max_length=500)


@router.post("/api/config/repeat-rule/signoff", tags=["config"], summary="Sign off the repeat rule, or ask for changes")
def signoff_rule(body: SignoffIn, user: dict = Depends(require("sign_off_rule"))):
    """Needs the ``sign_off_rule`` permission (the rule owner). Editing the rule afterwards voids the sign-off."""
    with connection() as conn:
        return rule_signoff.review(conn, user, body.decision, body.comment)


@router.put("/api/config/repeat-rule", tags=["config"], summary="Update repeat rule (edit_rule permission)")
def put_rule(body: RepeatRuleUpdate, user: dict = Depends(require("edit_rule"))):
    """Replace the repeat rule; creates a new rule version and an audit entry."""
    if not set(body.match_keys) <= {"customer_id", "site_id"}:
        raise ApiError(422, "invalid_match_keys", "match_keys must be a subset of customer_id, site_id.")
    if body.cause_mode not in ("level1", "level2", "none") or body.missing_values not in ("no_match", "ignore"):
        raise ApiError(422, "invalid_rule", "Invalid cause_mode or missing_values.")
    before = copy.deepcopy(get_config()["repeat_rule"])
    new = {**before, **body.model_dump(), "last_updated": db.now()}
    with connection() as conn:
        return {"repeat_rule": _override(conn, "repeat_rule", new, user, before)}


@router.put("/api/config/defaults", tags=["config"], summary="Update defaults (configure permission)")
def put_defaults(body: DefaultsUpdate, user: dict = Depends(require("configure"))):
    """Replace channel defaults; only known complaint types are accepted."""
    cfg = get_config()
    if not set(body.defaults) <= {t["id"] for t in cfg["types"]} | {"_all"}:
        raise ApiError(422, "invalid_type", "Unknown complaint type in defaults.")
    with connection() as conn:
        return {"defaults": _override(conn, "defaults", body.defaults, user, copy.deepcopy(cfg["defaults"]))}
