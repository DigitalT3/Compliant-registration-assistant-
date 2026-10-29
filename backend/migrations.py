"""Versioned, idempotent schema migrations for the PoC database (SQLite or Postgres).

Version 1 is the original schema created in ``db.initialize``. Version 2 adds the
entities required by the PoC specification (taxonomy, repeat evidence, events).
"""
from . import db as dbm


def _add_column(db, table: str, column: str, ddl: str) -> None:
    """Add ``column`` to ``table`` unless it already exists."""
    if column not in dbm.columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _migrate_v2(db) -> None:
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


def _migrate_v3(db) -> None:
    """Add the defaulted form fields (priority, owner team, response target, container)."""
    for table, column, ddl in [
        ("complaints", "priority", "TEXT"),
        ("complaints", "owner_team", "TEXT"),
        ("complaints", "response_target_days", "INTEGER"),
        ("complaints", "container", "TEXT"),
    ]:
        _add_column(db, table, column, ddl)


def _migrate_v4(db) -> None:
    """Store both taxonomy levels on each complaint (FR-11): category (level 1) next to the sub-cause."""
    _add_column(db, "complaints", "root_cause_category", "TEXT")


def _migrate_v5(db) -> None:
    """Support the timed user test: session mode and participant, baseline timings, exit interviews."""
    _add_column(db, "sessions", "mode", "TEXT DEFAULT 'assistant'")
    _add_column(db, "sessions", "participant_id", "TEXT")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS baseline(
      id INTEGER PRIMARY KEY, user_group TEXT NOT NULL, scenario TEXT, participant_id TEXT,
      seconds REAL NOT NULL, note TEXT, actor TEXT, at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS exit_interviews(
      id INTEGER PRIMARY KEY, participant_id TEXT NOT NULL, would_use_daily INTEGER NOT NULL,
      comment TEXT, actor TEXT, at TEXT NOT NULL);
    """)


def _migrate_v6(db) -> None:
    """Employee accounts: e-mail login, function category, approval status and lockout counters."""
    for column, ddl in [("email", "TEXT"), ("password_hash", "TEXT"), ("function", "TEXT"),
                        ("status", "TEXT DEFAULT 'active'"), ("created_at", "TEXT"), ("last_login_at", "TEXT"),
                        ("failed_logins", "INTEGER DEFAULT 0"), ("locked_until", "TEXT")]:
        _add_column(db, "users", column, ddl)
    db.executescript("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users(lower(email));
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


def _migrate_v7(db) -> None:
    """Admin-created accounts and password resets use a temporary password that must be changed at first sign-in."""
    _add_column(db, "users", "must_change_password", "INTEGER DEFAULT 0")


MIGRATIONS = {2: _migrate_v2, 3: _migrate_v3, 4: _migrate_v4, 5: _migrate_v5, 6: _migrate_v6, 7: _migrate_v7}


# PUBLIC_INTERFACE
def migrate(db) -> int:
    """Apply pending migrations in order and return the resulting user_version."""
    version = start = dbm.get_version(db)
    for target in sorted(MIGRATIONS):
        if target > version:
            MIGRATIONS[target](db)
            dbm.set_version(db, target)
            version = target
    if dbm.is_pg() and version != start:
        _lock_down(db)
    db.commit()
    return version


def _lock_down(db) -> None:
    """Supabase exposes public tables through its REST API: enable row-level security with no
    policies so the anon/authenticated roles can read and write nothing. The backend connects
    as the table owner, which is not affected."""
    db.executescript(";\n".join(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY'
                                for t in dbm.table_names(db) + ["schema_meta"]))
