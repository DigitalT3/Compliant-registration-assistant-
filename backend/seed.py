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
import os
import random
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from . import db
from .settings import invalidate_config

SEED_DIR = Path(__file__).resolve().parent / "seed_data"

N_CUSTOMERS = 34
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
    "access": ("De poort was afgesloten, de chauffeur kon er niet bij.", "The gate was locked, the driver could not reach the container."),
    "comms": ("Er is niet teruggebeld na onze melding.", "Nobody called back after our report."),
    "other": ("Ongebruikelijke synthetische situatie.", "Unusual synthetic situation."),
}
GENERATED_FIRST_SEQ = len(HISTORY) + 1
GENERATED_CAUSES = ["missed", "late", "damage", "access", "invoice", "conduct", "comms"]
GENERATED_OTHER_REASONS = ["Missing recycling certificate (synthetic)", "Request for site visit (synthetic)",
                           "Neighbour complaint about smell (synthetic)", "Question about waste legislation (synthetic)",
                           "Wrong contact person on file (synthetic)"]
OTHER_REASONS = {5: "Animal nest in container (synthetic)",
                 10: "Vandalised fence (synthetic)",
                 11: "Event road closure (synthetic)",
                 12: "Sensor test unit (synthetic)"}


def _cause_meta():
    return {c["id"]: c for c in db.config()["root_causes"]}


# Invented company names (no real businesses intended). Customers 1 and 2 share "Delta Works" on
# purpose so the name search is ambiguous (T04); customer 21 is the missing-data case.
NAMES = [
    "Delta Works Recycling BV", "Delta Works Logistiek BV", "Bakkerij De Gouden Korst BV",
    "Hoogendoorn Metaal BV", "Groenendaal Tuinbouw VOF", "Peeters Bouwmaterialen NV",
    "Jansen Horeca Groep BV", "De Vries Installatietechniek BV", "Zorgcentrum Het Anker",
    "Brouwer Transport BV", "Smit Schoonmaakdiensten BV", "Willems Aannemersbedrijf BV",
    "Kuipers Bouwbedrijf BV", "Dekker Kunststoffen BV", "Van Leeuwen Elektro BV",
    "Bos Fruitgroothandel BV", "De Jong Garagebedrijf BV", "Meijer Houthandel BV",
    "Hendriks Installatiebedrijf BV", "Boerenhof Kaasmakerij VOF", "Noordkade Metaalhandel BV",
    "Schouten Landbouwbedrijf VOF", "Vos Meubelfabriek BV", "Nijhuis Papierwaren BV",
    "Oosterhout Voedingsmiddelen BV", "Dekkers Printhuis BV", "Van der Heijden Slagerij",
    "Bloemendaal Tuincentrum BV", "Mol Verpakkingen BV", "De Schone Zaak Wasserij BV",
    "Kuyper Autodemontage BV", "Rijnmond Scheepsservice BV", "Maasland Bouwlogistiek BV",
    "Havenzicht Horeca BV",
]


def _cust_name(n: int) -> str:
    return NAMES[n - 1]


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
        conn.execute("INSERT INTO users(id,name,role,user_group,function) VALUES(?,?,?,?,?)",
                     (u["id"], u["name"], u["role"], u["group"], u.get("function")))
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
            conn.execute("INSERT INTO containers(id,customer_id,site_id,number,source) VALUES(?,?,?,?,'seed')",
                         (f"BOX-{n:03}-{s}", c, site, f"BOX-{n:03}-{s}"))
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


def _generated_history() -> list:
    """Deterministic extra history on customers 23-34 only, so scripted repeat cases are untouched.

    About a third of these are "Other" (together with the hand-written rows this mimics the
    ~40% "Other" baseline in the PRD).
    """
    rows = []
    for i in range(30):
        n = 23 + i % 12
        other = i % 3 == 0 or i % 10 == 7
        cause = "other" if other else GENERATED_CAUSES[i % len(GENERATED_CAUSES)]
        rows.append((GENERATED_FIRST_SEQ + i, n, 1 + i % 2, cause, ["open", "closed", "closed"][i % 3],
                     5 + (i * 17) % 165, "nl" if i % 2 else "en",
                     GENERATED_OTHER_REASONS[i % len(GENERATED_OTHER_REASONS)] if other else ""))
    return rows


HISTORY_FIRST_SEQ = GENERATED_FIRST_SEQ + 30          # the 12-month history continues the numbering
HISTORY_COMPLAINTS = 420                              # older than every hand-written row, so the repeat scenarios stay untouched
HISTORY_AGE_DAYS = (170, 364)                         # the repeat window is 60 days; the hand-written rows reach 165
HISTORY_OTHER_SHARE = 0.40                            # the "Other" baseline in the PRD (about 40%)

# Invented "Other" reasons per theme (English and Dutch), written the way an employee would type them; a few vague ones on purpose.
HISTORY_THEMES = {
    "wildlife": ["A seagull built a nest under the lid of the container", "Mice found in the paper container", "Een meeuw heeft een nest in de container gemaakt",
                 "Rats near the container area", "Vogels scheuren de zakken open", "Fox tipped over the bins overnight", "Muizen in de papiercontainer"],
    "road closure": ["The road was closed for a street parade, truck could not get through", "Weg afgesloten door een evenement, truck kon niet bij de container",
                     "Roadworks closed the whole street for a week", "Straat afgesloten voor wegwerkzaamheden", "Market day blocked the street"],
    "legislation": ["Customer asks which regulation applies to their waste", "Vraag over de nieuwe wetgeving voor bedrijfsafval", "Question whether a permit is needed for this container",
                    "Klant vraagt of er een vergunning nodig is", "Asks about the new rules for packaging waste"],
    "documents": ["Customer needs a certificate of disposal", "Waste declaration document was never sent", "Certificaat van vernietiging ontbreekt",
                  "Missing recycling certificate for the audit", "Afvalstroomovereenkomst nog niet ontvangen"],
    "smell": ["The neighbour complains about the smell from our container", "Buurman klaagt over stank bij de container", "Odour reported by the neighbours of the site",
              "Geuroverlast bij de buren van het terrein"],
    "site visit": ["Customer wants a site visit to discuss the setup", "Verzoek om een bezoek ter plaatse", "Asks for an inspection walk-through of the yard",
                   "Klant wil graag een locatiebezoek"],
    "contact": ["Wrong contact person on file", "Telefoonnummer van de contactpersoon klopt niet", "Our email address in your system is wrong",
                "Contactpersoon is niet meer in dienst"],
    "sensor": ["The pilot sensor on the container shows wrong data", "Test unit with GPS was not removed", "Sensor battery empty after the pilot", "Meter op de container geeft verkeerde waarden"],
}
HISTORY_VAGUE = ["See attachment", "Please call me", "Unclear reason, customer upset", "Zie bijlage", "Klant wil met de manager praten over iets anders"]
HISTORY_TEXT = {   # the free text of the other causes, more than one wording each
    "missed": ["Our container was not emptied on {day}.", "Collection was missed again this week.", "Onze container is {day} niet geleegd.", "De ophaling is gemist."],
    "late": ["The truck came {n} hours late.", "Driver arrived after the agreed time.", "De vuilniswagen kwam veel te laat.", "De inzameling was te laat."],
    "damage": ["The container lid is broken.", "Our bin was damaged during emptying.", "De container is kapot na de ophaling.", "Wiel van de container is afgebroken."],
    "access": ["The gate was locked and the driver left.", "Truck could not reach the container, blocked access.", "De poort was afgesloten, de chauffeur kon er niet bij."],
    "invoice": ["We were charged twice on the invoice.", "Invoice shows the wrong price.", "De factuur klopt niet, dubbel gefactureerd.", "Factuur bevat een verkeerd tarief."],
    "conduct": ["The driver was rude to our staff.", "Chauffeur was onbeleefd tegen onze medewerker.", "Driver left the gate open."],
    "comms": ["Nobody called back after our report.", "We were not informed about the changed collection day.", "Er is niet teruggebeld na onze melding."],
    "spillage": ["Waste spilled on the road during emptying.", "Afval op straat gevallen bij het legen."],
    "property_damage": ["The truck damaged our fence.", "Lorry drove through the gate and broke it.", "Vrachtwagen heeft ons hek beschadigd."],
    "weighing": ["The weighed amount on the ticket is wrong.", "Gewicht op de weegbon klopt niet."],
}


def _twelve_month_history() -> list:
    """Deterministic invented complaints for the 12 months before the anchor: ``(seq, customer no, site no, cause, status, age, language, reason, text, role)``.

    Shape of the PRD's 12-month extract (type, cause, free text, timestamps, creator role, status) with about 40% "Other". Spread over
    all customers and ages beyond the hand-written rows, so no seeded repeat scenario can see them (the repeat window is 60 days).
    """
    rnd = random.Random(20261028)
    causes = [c for c in HISTORY_TEXT]
    weights = [30, 18, 9, 8, 14, 6, 6, 3, 3, 3]
    themes = list(HISTORY_THEMES)
    rows = []
    for i in range(HISTORY_COMPLAINTS):
        n = rnd.randint(1, N_CUSTOMERS)
        site = 1 if n == MISSING_DATA_CUSTOMER else rnd.randint(1, 3 if n == EXTRA_SITE_CUSTOMER else 2)
        age, lang = rnd.randint(*HISTORY_AGE_DAYS), rnd.choice(["nl", "en"])
        status = rnd.choices(["closed", "open", "cancelled"], [90, 6, 4])[0]
        role = rnd.choices(["employee", "admin"], [94, 6])[0]
        if rnd.random() < HISTORY_OTHER_SHARE:
            reason = rnd.choice(HISTORY_VAGUE) if rnd.random() < 0.07 else rnd.choice(HISTORY_THEMES[rnd.choice(themes)])
            rows.append((HISTORY_FIRST_SEQ + i, n, site, "other", status, age, lang, reason, reason, role))
        else:
            cause = rnd.choices(causes, weights)[0]
            text = rnd.choice(HISTORY_TEXT[cause]).format(day=rnd.choice(["Monday", "Tuesday", "Thursday"]), n=rnd.randint(2, 5))
            rows.append((HISTORY_FIRST_SEQ + i, n, site, cause, status, age, lang, "", text, role))
    return rows


def _insert_history(conn, rows: list) -> int:
    """Insert history rows that are not there yet (by id); returns how many were added."""
    causes, cfg = _cause_meta(), db.config()
    anchor, added = db.seed_anchor(), 0
    for seq, n, s, cause, status, days, lang, reason, text, role in rows:
        cid = f"COM-SEED-{seq}"
        if conn.execute("SELECT 1 FROM complaints WHERE id=?", (cid,)).fetchone():
            continue
        c, site = f"C{n:03}", f"C{n:03}-S{s}"
        ctype = causes[cause].get("type") or "conduct"
        created = (anchor - timedelta(days=days)).isoformat()
        d = {**cfg["defaults"].get("_all", {}), **cfg["defaults"].get(ctype, {})}
        payload = {"description": text, "synthetic": True, "complaint_type": ctype, "other_reason": reason}
        conn.execute(
            "INSERT INTO complaints(id,customer_id,site_id,contract_id,order_id,root_cause,created,"
            "status,session_id,payload,channel,registration_date,registering_user,original_text,"
            "language,complaint_type,other_reason,taxonomy_version,is_poc,is_seed,priority,owner_team,"
            "response_target_days,container,root_cause_category,creator_role) VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,1,1,?,?,?,?,?,?)",
            (cid, c, site, f"{c}-K{s}", f"{c}-O{s}0", cause, created, status,
             json.dumps(payload), d.get("channel", "phone"), created, "seed", text, lang, ctype, reason,
             cfg["taxonomy_version"], d.get("priority"), d.get("owner_team"),
             int(d["response_target_days"]) if d.get("response_target_days") else None, f"BOX-{n:03}-{s}",
             causes[cause]["level1"], role))
        added += 1
    return added


def _seed_history(conn, anchor) -> None:
    rows = [(*h[:7], OTHER_REASONS.get(h[0], ""), TEXTS[h[3]][0 if h[6] == "nl" else 1], "admin" if h[0] % 17 == 0 else "employee") for h in HISTORY]
    rows += [(*g[:7], g[7], TEXTS[g[3]][0 if g[6] == "nl" else 1], "employee") for g in _generated_history()]
    _insert_history(conn, rows + _twelve_month_history())


# PUBLIC_INTERFACE
def add_history() -> int:
    """Top up an already seeded database with the 12-month history (idempotent); returns the number of rows added."""
    db.initialize()
    with db.connect() as conn:
        with db.pipeline(conn):
            return _insert_history(conn, _twelve_month_history())


# PUBLIC_INTERFACE
def seed(conn: sqlite3.Connection) -> None:
    """Insert all synthetic reference, customer and complaint data (assumes empty tables)."""
    anchor = db.seed_anchor()
    stamp = anchor.isoformat()
    with db.pipeline(conn):
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


def _truncate_current() -> bool:
    """Postgres fast path: if the schema is already at the latest version, empty the tables
    (identity counters restart) instead of dropping and recreating them. Returns True if done."""
    from . import migrations

    with db.connect() as conn:
        tables = db.table_names(conn)
        if not tables or db.get_version(conn) != max(migrations.MIGRATIONS):
            return False
        names = ", ".join(f'"{t}"' for t in tables)
        conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    return True


# PUBLIC_INTERFACE
def reset() -> None:
    """Explicitly drop every table in the PoC database, recreate the schema and reseed.

    Destructive by design; only call from the CLI ``--reset`` flag or tests. On a hosted Postgres database it refuses to touch the
    project's own schema (the one the live app uses) unless ``POC_ALLOW_LIVE_RESET=1`` is set on purpose; an isolated schema
    (``POC_PG_SCHEMA``, as the user-test script and the Postgres tests use) is fine.
    """
    if db.is_pg() and not os.environ.get("POC_PG_SCHEMA") and os.environ.get("POC_ALLOW_LIVE_RESET") != "1":
        raise RuntimeError("Refusing to reset the live Postgres schema: set POC_PG_SCHEMA to an isolated schema, or POC_ALLOW_LIVE_RESET=1 if you really mean it.")
    invalidate_config()
    if db.is_pg() and _truncate_current():
        seed_if_empty()
        return
    db.initialize()
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        for t in db.table_names(conn):
            conn.execute(f'DROP TABLE IF EXISTS "{t}"' + (" CASCADE" if db.is_pg() else ""))
        if db.is_pg():
            conn.execute("DROP TABLE IF EXISTS schema_meta")
        else:
            conn.execute("PRAGMA user_version=0")
        conn.commit()
    db.initialize()
    seed_if_empty()


# PUBLIC_INTERFACE
def fingerprint() -> dict:
    """Return per-table row counts and a SHA-256 over all table contents."""
    counts, digest = {}, hashlib.sha256()
    with db.connect() as conn:
        order = "1" if db.is_pg() else "rowid"
        for t in db.table_names(conn):
            rows = [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY {order}')]
            counts[t] = len(rows)
            digest.update(t.encode())
            digest.update(json.dumps(rows, default=str).encode())
        version = db.get_version(conn)
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
    p.add_argument("--add-history", action="store_true", help="add the synthetic 12-month complaint history to an already seeded database (idempotent)")
    args = p.parse_args(argv)
    if not (args.reset or args.seed or args.fingerprint or args.add_history):
        p.print_help()
        return 2
    if args.reset:
        reset()
        print(f"Reset and seeded {db.location()}")
    elif args.seed:
        print("Seeded" if seed_if_empty() else "Database not empty; nothing seeded")
    elif args.add_history:
        print(f"Added {add_history()} history complaints to {db.location()}")
    print(json.dumps(fingerprint(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
