"""Versioned, idempotent schema migrations for the PoC SQLite database.

Version 1 is the original schema created in ``db.initialize``. Version 2 adds the
entities required by the PoC specification (taxonomy, repeat evidence, events).
"""
import sqlite3


def _add_column(db: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add ``column`` to ``table`` unless it already exists."""
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _migrate_v2(db: sqlite3.Connection) -> None:
    """Extend v1 tables and add the new PoC tables and indexes."""
    for table, column, ddl in [
        ("customers", "active", "INTEGER DEFAULT 1"),
        ("customers", "created_at", "TEXT"),
        ("sites", "reference", "TEXT"),
        ("sites", "postcode", "TEXT"),
        ("sites", "active", "INTEGER DEFAULT 1"),
        ("contracts", "reference", "TEXT"),
        ("contracts", "valid_from", "TEXT"),
        ("contracts", "valid_to", "TEXT"),
        ("orders", "reference", "TEXT"),
        ("sessions", "current_step", "TEXT"),
        ("sessions", "failure_status", "TEXT"),
        ("sessions", "scenario", "TEXT"),
        ("sessions", "user_group", "TEXT"),
        ("complaints", "channel", "TEXT"),
        ("complaints", "registration_date", "TEXT"),
        ("complaints", "registering_user", "TEXT"),
        ("complaints", "original_text", "TEXT"),
        ("complaints", "language", "TEXT"),
        ("complaints", "summary_json", "TEXT"),
        ("complaints", "summary_meta", "TEXT"),
        ("complaints", "complaint_type", "TEXT"),
        ("complaints", "other_reason", "TEXT"),
        ("complaints", "rule_version", "TEXT"),
        ("complaints", "taxonomy_version", "TEXT"),
        ("complaints", "repeat_detected", "INTEGER"),
        ("complaints", "scenario", "TEXT"),
        ("complaints", "is_poc", "INTEGER DEFAULT 1"),
        ("complaints", "is_seed", "INTEGER DEFAULT 0"),
    ]:
        _add_column(db, table, column, ddl)

    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, user_group TEXT);
    CREATE TABLE IF NOT EXISTS complaint_types(
      id TEXT PRIMARY KEY, code TEXT UNIQUE, name_en TEXT, name_nl TEXT,
      description TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS root_causes(
      id INTEGER PRIMARY KEY, code TEXT NOT NULL, level1 TEXT, level2 TEXT,
      label_en TEXT, label_nl TEXT, definition TEXT, examples TEXT,
      taxonomy_version TEXT NOT NULL, active INTEGER DEFAULT 1,
      UNIQUE(code, taxonomy_version));
    CREATE TABLE IF NOT EXISTS config_versions(
      id INTEGER PRIMARY KEY, kind TEXT NOT NULL, version TEXT NOT NULL,
      content TEXT, activated_at TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS step_events(
      id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
      step TEXT NOT NULL, event_type TEXT NOT NULL, at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS field_events(
      id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
      field TEXT NOT NULL, origin TEXT, event_type TEXT, changed INTEGER DEFAULT 0,
      value_repr TEXT, at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ai_events(
      id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
      operation TEXT NOT NULL, provider TEXT, model TEXT, prompt_version TEXT,
      candidates TEXT, selected TEXT, in_top3 INTEGER, duration_ms INTEGER,
      status TEXT, error_category TEXT, at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS repeat_checks(
      id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
      complaint_id TEXT REFERENCES complaints(id), rule_version TEXT,
      input_hash TEXT, is_repeat INTEGER, matching_ids TEXT, explanation TEXT,
      checked_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS repeat_disputes(
      id INTEGER PRIMARY KEY, repeat_check_id INTEGER REFERENCES repeat_checks(id),
      complaint_id TEXT REFERENCES complaints(id), prior_complaint_id TEXT,
      decision TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT,
      rule_version TEXT, evidence TEXT, at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_reference ON orders(reference);
    CREATE INDEX IF NOT EXISTS ix_orders_container ON orders(container);
    CREATE INDEX IF NOT EXISTS ix_complaints_cust_site ON complaints(customer_id, site_id);
    CREATE INDEX IF NOT EXISTS ix_step_events_session ON step_events(session_id);
    CREATE INDEX IF NOT EXISTS ix_field_events_session ON field_events(session_id);
    CREATE INDEX IF NOT EXISTS ix_ai_events_session ON ai_events(session_id);
    """)


MIGRATIONS = {2: _migrate_v2}


# PUBLIC_INTERFACE
def migrate(db: sqlite3.Connection) -> int:
    """Apply pending migrations in order and return the resulting user_version."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    for target in sorted(MIGRATIONS):
        if target > version:
            MIGRATIONS[target](db)
            db.execute(f"PRAGMA user_version={int(target)}")
            version = target
    db.commit()
    return version
