"""FR-15 check: is the log complete for every test registration?

    python -m scripts.log_check --url http://127.0.0.1:8001 --email admin@example.nl

Needs an administrator (or governance) account: it reads the Audit Trail. Signs in like the browser (hidden password prompt,
or CHECK_PASSWORD), lists every registration made in the app (not the synthetic history) and reports, for each, whether its log
is complete (time per step for all five steps, fields prefilled, origin of all 15 fields at save, the suggestions shown and what
was accepted or changed) and what is missing when it is not. Read-only.
"""
import argparse
import getpass
import os
import sys

from scripts.requirements_check import Api


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    a = ap.parse_args()
    api = Api(a.url)
    login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": os.environ.get("CHECK_PASSWORD") or getpass.getpass("Password: ")})
    if not login.get("token") or login.get("must_change_password"):
        print("Sign-in failed or a password change is pending.")
        return 2
    api.token = login["token"]
    records, page = [], 1
    while True:
        r, _ = api.call("GET", "/api/audit/records", params={"include_seed": "false", "page": page, "page_size": 100})
        if "items" not in r:
            print("Not allowed or failed:", r.get("error", r))
            return 2
        records += r["items"]
        if page * 100 >= r["total"]:
            break
        page += 1
    complete = [x for x in records if x["log"] == "complete"]
    print(f"{len(complete)} of {len(records)} registrations made in the app have a complete log\n")
    for x in records:
        if x["log"] == "complete":
            continue
        d, _ = api.call("GET", f"/api/audit/records/{x['id']}")
        print(f"  {x['id']}  incomplete: {', '.join(d['log'].get('missing', []))}")
    sample = next((x for x in complete), None)
    if sample:
        d, _ = api.call("GET", f"/api/audit/records/{sample['id']}")
        lg = d["log"]
        print(f"\nExample, {sample['id']}: {lg['mode']} mode, {lg['total_seconds']} s in total; " + ", ".join(f"{s['step']} {s['seconds']} s" for s in lg["steps"]))
        print(f"  prefilled {lg['prefilled_at_start']['prefilled']}, defaulted {lg['prefilled_at_start']['default']}; at save {lg['fields_at_save']}; "
              f"suggestions shown {len(lg['suggestions']['causes'])}, cause: {lg['suggestions']['cause_result']}, summary: {lg['suggestions']['summary_result']}")
    return 0 if len(complete) == len(records) else 1


if __name__ == "__main__":
    sys.exit(main())
