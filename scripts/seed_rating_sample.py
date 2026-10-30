"""Set up the process-owner rating (FR-08) in the database the app is configured for.

    python -m scripts.seed_rating_sample              # create the evaluator account and the 10 complaints to rate
    python -m scripts.seed_rating_sample --remove     # delete those complaints and their ratings again (the account stays)

It (1) creates an account with the evaluator role (temporary password, changed at the first sign-in) and writes its
sign-in details to a git-ignored file, never to the terminal, and (2) saves the ten typical synthetic complaints of
tests/acceptance/summary_cases.json with a summary made by the configured model, so they appear on the owner's
Evaluation page ("Blind labelling") to be rated. The complaints carry the scenario tag "rating-sample-Sxx", are
registered under a demo employee and have no session, so they do not touch the timing statistics. Running it again
adds nothing that already exists. Uses the database selected by POC_DB / DATABASE_URL / POC_PG_SCHEMA.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from backend import db
from backend.dbutil import audit, connection
from backend.services import accounts, ai, complaints
from backend.settings import get_config

ROOT = Path(__file__).resolve().parents[1]
TAG = "rating-sample-"
# (customer, site) per case. None of these customers appears in the seeded repeat scenarios (backend/seed_data/scenarios.json):
# a sample complaint saved there would become repeat history and change the answers the repeat rule must give (FR-12).
PLACES = [("C005", "C005-S1"), ("C005", "C005-S2"), ("C008", "C008-S1"), ("C008", "C008-S2"), ("C011", "C011-S1"),
          ("C011", "C011-S2"), ("C012", "C012-S1"), ("C017", "C017-S1"), ("C018", "C018-S1"), ("C019", "C019-S2")]


def create_account(conn, email: str, name: str, out: Path) -> str:
    row = conn.execute("SELECT id, role FROM users WHERE lower(email)=?", (email.lower(),)).fetchone()
    if row:
        print(f"Account {email} already exists (role {row['role']}); not touched, no new password.")
        return row["id"]
    temp = accounts.temporary_password()
    uid = accounts.create_account(conn, None, name, email, temp, None, "evaluator", must_change=True)
    audit(conn, uid, "account_created_by_operator", {"user": uid, "role": "evaluator", "via": "scripts.seed_rating_sample"})
    conn.commit()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"Process owner test account (role: evaluator)\n\nE-mail:             {email}\nTemporary password: {temp}\n\n"
                   "You must choose your own password at the first sign-in. Keep this file private (it is git-ignored).\n", encoding="utf-8")
    out.chmod(0o600)
    print(f"Account created: {email} (evaluator). Sign-in details written to {out}")
    return uid


def remove(conn) -> None:
    ids = [r["id"] for r in conn.execute("SELECT id FROM complaints WHERE scenario LIKE ?", (TAG + "%",))]
    for cid in ids:
        for table in ("evaluations", "repeat_checks", "repeat_disputes"):
            conn.execute(f"DELETE FROM {table} WHERE complaint_id=?", (cid,))
        conn.execute("DELETE FROM complaints WHERE id=?", (cid,))
    conn.commit()
    print(f"Removed {len(ids)} rating-sample complaints and their ratings.")


def seed_complaints(conn) -> None:
    cases = json.loads((ROOT / "tests/acceptance/summary_cases.json").read_text(encoding="utf-8"))["cases"]
    demo = conn.execute("SELECT id, name FROM users WHERE id='demo.emp.a1'").fetchone()
    if not demo:
        raise SystemExit("The demo employee 'demo.emp.a1' is missing in this database; cannot register the sample complaints.")
    user, cfg, made = {"id": demo["id"], "name": demo["name"], "role": "employee"}, get_config(), 0
    for case, (customer, site) in zip(cases, PLACES):
        scenario = TAG + case["id"]
        there = conn.execute("SELECT id, customer_id, site_id FROM complaints WHERE scenario=?", (scenario,)).fetchone()
        if there:
            if (there["customer_id"], there["site_id"]) != (customer, site):       # an earlier version placed it on a scenario customer
                conn.execute("UPDATE complaints SET customer_id=?, site_id=?, contract_id=NULL, order_id=NULL, container=NULL WHERE id=?", (customer, site, there["id"]))
                conn.commit()
                print(f"  {case['id']}: {there['id']} moved to {customer}/{site}")
            else:
                print(f"  {case['id']}: already there")
            continue
        site_name = conn.execute("SELECT name FROM sites WHERE id=?", (site,)).fetchone()["name"]
        out = ai.run(conn, "analyze", {"text": case["text"], "language": None, "site_name": site_name, "complaint_type": case["type"],
                                       "taxonomy": cfg["root_causes"], "types": [t["id"] for t in cfg["types"]],
                                       "template_extras_by_type": cfg["summary"]["by_type"]}, None, user["id"])
        if out["ai_status"] != "ok":
            print(f"  {case['id']}: the model did not answer ({out.get('error_category')}); skipped, run again later")
            continue
        summary = out["result"]["summary"]
        top = (out["result"]["classification"]["candidates"] or [{}])[0].get("root_cause_id") or "other"
        saved = complaints.create(conn, {
            "customer_id": customer, "site_id": site, "channel": "phone", "complaint_type": case["type"], "root_cause": top,
            "other_reason": "rating sample" if top == "other" else None, "description": case["text"], "language": case["language"],
            "summary": summary, "summary_meta": {"mock": False}, "scenario": scenario}, user)
        made += 1
        print(f"  {case['id']}: saved as {saved['id']} ({case['type']}, {case['language']})")
    print(f"{made} complaints created.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="process.owner.test@example.nl")
    ap.add_argument("--name", default="Process Owner (test)")
    ap.add_argument("--credentials-file", default=str(ROOT / ".local" / "process-owner-account.txt"))
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    db.initialize()
    with connection() as conn:
        if a.remove:
            remove(conn)
        else:
            create_account(conn, a.email, a.name, Path(a.credentials_file))
            seed_complaints(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
