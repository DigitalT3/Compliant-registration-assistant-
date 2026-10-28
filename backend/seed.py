"""Deterministic synthetic seed data and explicit reset CLI.

Usage (from the project root)::

    python -m backend.seed --reset         # drop all PoC tables, recreate, reseed
    python -m backend.seed --seed          # seed only if the database is empty
    python -m backend.seed --fingerprint   # print row counts and a content hash

All data is fictional. Nothing here contacts any external system.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from . import db

SEED_DIR = Path(__file__).resolve().parent / "seed_data"

N_CUSTOMERS = 22
EXTRA_SITE_CUSTOMER = 3      # has a third site (multiple-site case)
MISSING_DATA_CUSTOMER = 21   # one site, expired contract, no postcode, few orders

# (seq, customer no, site no, cause, status, age in days, language)
HISTORY = [
    (1, 1, 1, "missed", "open", 5, "en"), (2, 2, 1, "missed", "closed", 80, "nl"),
    (3, 3, 1, "missed", "cancelled", 3, "en"), (4, 4, 1, "invoice", "open", 4, "nl"),
    (5, 5, 1, "other", "closed", 6, "en"), (6, 6, 1, "late", "open", 10, "nl"),
    (7, 6, 1, "late", "closed", 20, "en"), (8, 7, 1, "damage", "open", 7, "nl"),
    (9, 8, 1, "missed", "open", 8, "en"), (10, 11, 1, "other", "closed", 15, "nl"),
    (11, 12, 1, "other", "closed", 30, "en"), (12, 13, 1, "other", "open", 45, "nl"),
    (13, 14, 1, "conduct", "closed", 59, "en"), (14, 15, 1, "invoice", "open", 60, "nl"),
    (15, 16, 1, "invoice", "open", 61, "en"),
]
TEXTS = {
    "missed": ("Onze container is niet geleegd.", "Our container was not emptied."),
    "late": ("De inzameling was te laat.", "The collection was late."),
    "damage": ("De container is kapot.", "The container is damaged."),
    "invoice": ("De factuur klopt niet.", "The invoice is incorrect."),
    "conduct": ("De chauffeur was onbeleefd.", "The driver was rude."),
    "other": ("Ongebruikelijke synthetische situatie.", "Unusual synthetic situation."),
}
OTHER_REASONS = {5: "Animal nest in container (synthetic)",
                 10: "Vandalised fence (synthetic)",
                 11: "Event road closure (synthetic)",
                 12: "Sensor test unit (synthetic)"}


def _cause_meta():
    return {c["id"]: c for c in db.config()["root_causes"]}


def _cust_name(n: int) -> str:
    if n < 3:
        return f"Fictional Delta Works {n:02}"
    if n >= 21:
        return f"Fictional Noord Recycling {n:02}"
    return f"Fictional Circular Works {n:02}"


def _seed_reference(conn, stamp: str) -> None:
    cfg = db.config()
    for t in cfg["types"]:
        conn.execute("INSERT INTO complaint_types VALUES(?,?,?,?,?,1)",
                     (t["id"], t["id"], t["en"], t["nl"], t.get("description", "")))
    for c in cfg["root_causes"]:
        conn.execute(
            "INSERT INTO root_causes(code,level1,level2,label_en,label_nl,definition,examples,"
            "taxonomy_version,active) VALUES(?,?,?,?,?,?,?,?,1)",
            (c["id"], c["level1"], c.get("level2"), c["en"], c["nl"], c["definition"],
             c["examples"], cfg["taxonomy_version"]))
    for u in cfg["demo_users"]:
        conn.execute("INSERT INTO users VALUES(?,?,?,?)", (u["id"], u["name"], u["role"], u["group"]))
    for kind, version, content in [
        ("defaults", cfg["version"], cfg["defaults"]),
        ("taxonomy", cfg["taxonomy_version"], cfg["root_causes"]),
        ("repeat_rule", cfg["repeat_rule"]["version"], cfg["repeat_rule"]),
        ("summary_template", cfg["summary"]["template_version"], cfg["summary"]),
        ("classification", cfg["classification"]["version"], cfg["classification"]),
    ]:
        conn.execute("INSERT INTO config_versions(kind,version,content,activated_at,active) "
                     "VALUES(?,?,?,?,1)", (kind, version, json.dumps(content, sort_keys=True), stamp))


def _seed_customers(conn, anchor, stamp: str) -> None:
    for n in range(1, N_CUSTOMERS + 1):
        c = f"C{n:03}"
        postcode = None if n == MISSING_DATA_CUSTOMER else f"{1000 + n}ZZ"
        conn.execute("INSERT INTO customers(id,number,name,postcode,active,created_at) "
                     "VALUES(?,?,?,?,1,?)", (c, f"100{n:03}", _cust_name(n), postcode, stamp))
        n_sites = 3 if n == EXTRA_SITE_CUSTOMER else 1 if n == MISSING_DATA_CUSTOMER else 2
        n_orders = 2 if n == MISSING_DATA_CUSTOMER else 6
        for s in range(1, n_sites + 1):
            site, contract = f"{c}-S{s}", f"{c}-K{s}"
            conn.execute("INSERT INTO sites(id,customer_id,name,reference,postcode,active) "
                         "VALUES(?,?,?,?,?,1)",
                         (site, c, f"Synthetic depot {s}", f"SITE-{n:03}-{s}", postcode))
            expired = n == MISSING_DATA_CUSTOMER
            conn.execute(
                "INSERT INTO contracts(id,customer_id,site_id,status,reference,valid_from,valid_to) "
                "VALUES(?,?,?,?,?,?,?)",
                (contract, c, site, "expired" if expired else "active", f"CON-{n:03}-{s}",
                 (anchor - timedelta(days=400)).date().isoformat(),
                 (anchor - timedelta(days=10) if expired else anchor + timedelta(days=300)).date().isoformat()))
            for k in range(n_orders):
                conn.execute(
                    "INSERT INTO orders(id,customer_id,site_id,contract_id,container,date,status,reference) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (f"{c}-O{s}{k}", c, site, contract, f"BOX-{n:03}-{s}",
                     (anchor - timedelta(days=k * 12 + s)).isoformat(),
                     "in_progress" if k == 0 else "completed", f"ORD-{n:03}-{s}{k}"))


def _seed_history(conn, anchor) -> None:
    causes, cfg = _cause_meta(), db.config()
    for seq, n, s, cause, status, days, lang in HISTORY:
        c, site = f"C{n:03}", f"C{n:03}-S{s}"
        text = TEXTS[cause][0 if lang == "nl" else 1]
        ctype = causes[cause]["level1"] if causes[cause]["level1"] != "other" else "conduct"
        created = (anchor - timedelta(days=days)).isoformat()
        payload = {"description": text, "synthetic": True, "complaint_type": ctype,
                   "other_reason": OTHER_REASONS.get(seq, "")}
        conn.execute(
            "INSERT INTO complaints(id,customer_id,site_id,contract_id,order_id,root_cause,created,"
            "status,session_id,payload,channel,registration_date,registering_user,original_text,"
            "language,complaint_type,other_reason,taxonomy_version,is_poc,is_seed) "
            "VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,1,1)",
            (f"POC-SEED-{seq}", c, site, f"{c}-K{s}", f"{c}-O{s}0", cause, created, status,
             json.dumps(payload), cfg["defaults"].get(ctype, {}).get("channel", "phone"), created,
             "seed", text, lang, ctype, OTHER_REASONS.get(seq, ""), cfg["taxonomy_version"]))


# PUBLIC_INTERFACE
def seed(conn: sqlite3.Connection) -> None:
    """Insert all synthetic reference, customer and complaint data (assumes empty tables)."""
    anchor = db.seed_anchor()
    stamp = anchor.isoformat()
    _seed_reference(conn, stamp)
    _seed_customers(conn, anchor, stamp)
    _seed_history(conn, anchor)


# PUBLIC_INTERFACE
def seed_if_empty() -> bool:
    """Seed the database only when it has no customers. Returns True if seeded."""
    db.initialize()
    with db.connect() as conn:
        if conn.execute("SELECT count(*) FROM customers").fetchone()[0]:
            return False
        seed(conn)
    return True


# PUBLIC_INTERFACE
def reset() -> None:
    """Explicitly drop every table in the PoC database, recreate the schema and reseed.

    Destructive by design; only call from the CLI ``--reset`` flag or tests.
    """
    db.initialize()
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{t}"')
        conn.execute("PRAGMA user_version=0")
        conn.commit()
    db.initialize()
    seed_if_empty()


# PUBLIC_INTERFACE
def fingerprint() -> dict:
    """Return per-table row counts and a SHA-256 over all table contents."""
    counts, digest = {}, hashlib.sha256()
    with db.connect() as conn:
        tables = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        for t in tables:
            rows = [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid')]
            counts[t] = len(rows)
            digest.update(t.encode())
            digest.update(json.dumps(rows, default=str).encode())
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return {"user_version": version, "counts": counts, "sha256": digest.hexdigest()}


# PUBLIC_INTERFACE
def load_scenarios() -> list:
    """Load the scripted synthetic scenario definitions."""
    return json.loads((SEED_DIR / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def main(argv=None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Seed or reset the synthetic PoC database.")
    p.add_argument("--reset", action="store_true", help="DESTRUCTIVE: drop all PoC tables and reseed")
    p.add_argument("--seed", action="store_true", help="seed only if the database is empty")
    p.add_argument("--fingerprint", action="store_true", help="print counts and content hash")
    args = p.parse_args(argv)
    if not (args.reset or args.seed or args.fingerprint):
        p.print_help()
        return 2
    if args.reset:
        reset()
        print(f"Reset and seeded {db.db_path()}")
    elif args.seed:
        print("Seeded" if seed_if_empty() else "Database not empty; nothing seeded")
    print(json.dumps(fingerprint(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
