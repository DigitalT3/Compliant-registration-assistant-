"""SQLite persistence for synthetic PoC records only."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = str(ROOT / "poc.sqlite3")
# Kept for backwards compatibility; connect() re-reads POC_DB_PATH on each call.
DB_PATH = os.environ.get("POC_DB_PATH", DEFAULT_DB_PATH)

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  id TEXT PRIMARY KEY, number TEXT UNIQUE, name TEXT, postcode TEXT);
CREATE TABLE IF NOT EXISTS sites(
  id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers(id), name TEXT);
CREATE TABLE IF NOT EXISTS contracts(
  id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers(id),
  site_id TEXT REFERENCES sites(id), status TEXT);
CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers(id),
  site_id TEXT REFERENCES sites(id), contract_id TEXT REFERENCES contracts(id),
  container TEXT, date TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, actor TEXT, started TEXT, ended TEXT,
  status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
  kind TEXT, at TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS complaints(
  id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers(id),
  site_id TEXT REFERENCES sites(id), contract_id TEXT REFERENCES contracts(id),
  order_id TEXT REFERENCES orders(id), root_cause TEXT, created TEXT,
  status TEXT, session_id TEXT UNIQUE REFERENCES sessions(id), payload TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, actor TEXT, action TEXT, at TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS evaluations(
  id INTEGER PRIMARY KEY, complaint_id TEXT REFERENCES complaints(id),
  actor TEXT, usable INTEGER, expert_cause TEXT, notes TEXT, at TEXT);
"""


# PUBLIC_INTERFACE
def now():
    """Return an aware UTC timestamp (ISO-8601 string)."""
    return datetime.now(timezone.utc).isoformat()


# PUBLIC_INTERFACE
def db_path() -> str:
    """Return the active database path (``POC_DB_PATH`` env var or default)."""
    return os.environ.get("POC_DB_PATH", DEFAULT_DB_PATH)


# PUBLIC_INTERFACE
def connect():
    """Open a foreign-key-enforcing connection; caller owns its lifetime."""
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# PUBLIC_INTERFACE
def config():
    """Read the single source of provisional business configuration."""
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


# PUBLIC_INTERFACE
def seed_anchor() -> datetime:
    """Return the fixed anchor date used for seeded data.

    ``POC_SEED_ANCHOR`` (ISO date-time or ``today``) overrides ``seed.anchor_date``
    in config.json. A fixed anchor keeps seeded data identical on every day.
    """
    raw = os.environ.get("POC_SEED_ANCHOR") or config()["seed"]["anchor_date"]
    if raw == "today":
        return datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# PUBLIC_INTERFACE
def reference_now() -> datetime:
    """Return the 'current' time used by business rules such as repeat detection.

    ``POC_CLOCK_MODE`` (``fixed`` or ``real``) overrides ``seed.clock_mode``. In
    ``fixed`` mode the seed anchor is used so seeded repeat scenarios stay valid.
    """
    mode = os.environ.get("POC_CLOCK_MODE") or config()["seed"].get("clock_mode", "fixed")
    return seed_anchor() if mode == "fixed" else datetime.now(timezone.utc)


# PUBLIC_INTERFACE
def initialize(seed: bool = False):
    """Create the schema (v1 base plus migrations) and optionally seed if empty.

    Seeding lives in ``backend.seed``; it is never run destructively from here.
    """
    from . import migrations

    with connect() as conn:
        conn.executescript(BASE_SCHEMA)
        if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
            conn.execute("PRAGMA user_version=1")
        migrations.migrate(conn)
    if seed:
        from . import seed as seed_module

        seed_module.seed_if_empty()
