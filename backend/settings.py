"""Effective configuration: config.json + runtime overrides + environment variables."""
import json
import os
import sqlite3

from . import db

OVERRIDABLE = ("repeat_rule", "defaults")


# PUBLIC_INTERFACE
def get_config() -> dict:
    """Return config.json overlaid with the latest active admin override rows.

    Overrides live in ``config_versions`` (versions prefixed ``override-``) so the
    file stays the pristine default and every change is versioned and audited.
    """
    cfg = db.config()
    try:
        with db.connect() as conn:
            for kind in OVERRIDABLE:
                row = conn.execute(
                    "SELECT content FROM config_versions WHERE kind=? AND active=1 "
                    "AND version LIKE 'override-%' ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
                if row:
                    cfg[kind] = json.loads(row["content"])
    except sqlite3.Error:
        pass  # database not initialised yet: file defaults apply
    return cfg


# PUBLIC_INTERFACE
def ai_settings() -> dict:
    """Return AI settings; environment variables take precedence over config.json."""
    base = dict(db.config()["ai"])
    env = os.environ
    return {
        "provider": (env.get("AI_PROVIDER") or base["provider"]).lower(),
        "model": env.get("AI_MODEL") or base["model"],
        "base_url": env.get("AI_BASE_URL", ""),
        "api_key": env.get("AI_API_KEY", ""),
        "timeout_s": float(env.get("AI_TIMEOUT_S") or base["timeout_s"]),
        "max_retries": int(env.get("AI_MAX_RETRIES") or base["max_retries"]),
        "max_input_chars": int(env.get("AI_MAX_INPUT_CHARS") or base["max_input_chars"]),
    }


# PUBLIC_INTERFACE
def max_body_bytes() -> int:
    """Maximum accepted request body size in bytes (``MAX_BODY_BYTES``, default 64 KiB)."""
    return int(os.environ.get("MAX_BODY_BYTES", "65536"))


# PUBLIC_INTERFACE
def abandon_after_minutes() -> int:
    """Idle minutes after which an active session counts as abandoned."""
    return int(os.environ.get("ABANDON_AFTER_MINUTES", "30"))


# PUBLIC_INTERFACE
def causes_by_id(cfg: dict | None = None) -> dict:
    """Map root-cause id to its taxonomy entry."""
    return {c["id"]: c for c in (cfg or get_config())["root_causes"]}
