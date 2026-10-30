"""FR-12 and FR-13 check against a RUNNING app with a real account (no demo header).

    python -m scripts.repeat_check --url http://127.0.0.1:8001 --email you@example.nl [--save]

FR-12: for the eleven seeded repeat scenarios (backend/seed_data/scenarios.json, T10 to T20) it asks the app the same question
the screen asks before saving ("check-repeat") and compares: every seeded repeat is flagged with its linked earlier complaints,
and no seeded non-repeat is flagged. Seed ids are compared as COM-SEED (older databases hold POC-SEED). It stores one
repeat-check row per scenario and nothing else. If a scenario differs, the complaints saved in this database since the seeding
(test complaints) are listed: they are history too, so use a clean database for the real test (scripts/run_usertest.sh).
FR-13 (needs --save, saves one test complaint): confirms one linked earlier complaint, disputes another with a reason, and checks both
are logged next to the unchanged rule result, that a dispute without a reason or about a complaint that is not linked is refused.
"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from scripts.requirements_check import Api, report, RESULTS

ROOT = Path(__file__).resolve().parents[1]
norm = lambda ids: [i.replace("POC-SEED", "COM-SEED") for i in ids]


def fr12(api, customers):
    scenarios = [s for s in json.loads((ROOT / "backend/seed_data/scenarios.json").read_text(encoding="utf-8"))["scenarios"] if s.get("repeat_candidate")]
    wrong, repeats, non_repeats, flagged_ok, quiet_ok, evidence_ok = [], 0, 0, 0, 0, True
    for s in scenarios:
        cand, want = s["repeat_candidate"], s["expected"]
        out, _ = api.call("POST", "/api/complaints/check-repeat", {k: cand[k] for k in ("customer_id", "site_id", "root_cause")})
        got = norm([m["id"] for m in out.get("matches", [])])
        if want["repeat"]:
            repeats += 1
            flagged_ok += out.get("is_repeat") is True and got == want["matches"]
            evidence_ok &= all(m.get("id") and (m.get("date") or m.get("created")) and m.get("status") for m in out.get("matches", []))
        else:
            non_repeats += 1
            quiet_ok += out.get("is_repeat") is False and not got
        if out.get("is_repeat") != want["repeat"] or got != want["matches"]:
            wrong.append((s["id"], want["repeat"], out.get("is_repeat"), got))
    report("FR-12", "100% of seeded repeats flagged, linked earlier complaints shown", flagged_ok == repeats and evidence_ok,
           f"{flagged_ok} of {repeats} seeded repeats flagged with the expected linked complaints (id, date, status shown: {evidence_ok})")
    report("FR-12", "no flag on seeded non-repeats", quiet_ok == non_repeats, f"{quiet_ok} of {non_repeats} seeded non-repeats unflagged")
    if wrong:
        print("         differing scenarios:", wrong)
        listing, _ = api.call("GET", "/api/complaints", params={"page_size": 200, "include_seed": "false"})
        extra = [(c["id"], c["customer_id"], c["site_id"], c["root_cause"]) for c in listing.get("items", [])
                 if c["customer_id"] in {s["repeat_candidate"]["customer_id"] for s in scenarios}]
        print(f"         complaints saved since the seeding on those customers (they count as history): {extra[:8]}")


def fr13(api, me, save):
    if not save:
        print("  [skip] FR-13 confirm / dispute with a reason: run with --save (saves 1 test complaint)")
        return
    cand = next(s for s in json.loads((ROOT / "backend/seed_data/scenarios.json").read_text(encoding="utf-8"))["scenarios"] if s["id"] == "T14")["repeat_candidate"]
    check, _ = api.call("POST", "/api/complaints/check-repeat", {k: cand[k] for k in ("customer_id", "site_id", "root_cause")})
    priors = [m["id"] for m in check["matches"]]
    if len(priors) < 2:
        report("FR-13", "confirm or dispute a repeat link", False, f"T14 should link two earlier complaints, found {priors}")
        return
    body = {**cand, "channel": "phone", "complaint_type": "service", "description": "Repeat check test complaint (synthetic).",
            "repeat_decisions": [{"prior_complaint_id": priors[0], "decision": "confirm"},
                                 {"prior_complaint_id": priors[1], "decision": "reject", "reason": "Different container, not the same problem"}]}
    refused, _ = api.call("POST", "/api/complaints", {**body, "repeat_decisions": [{"prior_complaint_id": priors[1], "decision": "reject"}]})
    saved, _ = api.call("POST", "/api/complaints", body)
    cid = saved.get("id")
    rec, _ = api.call("GET", f"/api/complaints/{cid}") if cid else ({}, 0)
    logged = {d["prior_complaint_id"]: d for d in rec.get("repeat_disputes", [])}
    listing, _ = api.call("GET", "/api/repeat-disputes")
    seen = [d for d in listing.get("items", []) if d["complaint_id"] == cid]
    stray, _ = api.call("POST", "/api/repeat-disputes", {"complaint_id": cid, "prior_complaint_id": "COM-SEED-1", "decision": "reject", "reason": "not linked"})
    ok = (refused.get("_status") == 422 and refused.get("error", {}).get("code") == "reason_required"
          and saved.get("repeat", {}).get("is_repeat") is True                                      # the rule outcome is unchanged
          and set(logged) == set(priors[:2]) and logged[priors[0]]["decision"] == "confirm" and logged[priors[1]]["decision"] == "reject"
          and logged[priors[1]]["reason"].startswith("Different container") and json.loads(logged[priors[1]]["evidence"] or "{}").get("is_repeat")
          and len(seen) == 2 and seen[0].get("actor_name") == me["name"] and stray.get("_status") == 422)
    report("FR-13", "confirm or dispute a repeat link with a reason; logged for review", ok,
           f"saved {cid}: confirmed {priors[0]}, disputed {priors[1]} with a reason; a dispute without a reason refused ({refused.get('_status')}), "
           f"an unlinked complaint refused ({stray.get('_status')}); {len(seen)} decisions listed with who, when and the rule evidence")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    api = Api(a.url)
    if api.call("GET", "/api/auth/me")[0].get("_status") != 401:
        print("The app answered without sign-in: not in real mode. Stopping.")
        return 2
    login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": os.environ.get("CHECK_PASSWORD") or getpass.getpass("Password: ")})
    if not login.get("token") or login.get("must_change_password"):
        print("Sign-in failed or a password change is pending.")
        return 2
    api.token = login["token"]
    me, _ = api.call("GET", "/api/auth/me")
    rule = api.call("GET", "/api/config/repeat-rule")[0]
    print(f"Signed in as {me['name']} ({me['role']}), demo mode off; repeat rule {rule['repeat_rule']['version']}: {rule['repeat_rule']['lookback_days']} days, match {', '.join(rule['repeat_rule']['match_keys'])}, cause level {rule['repeat_rule']['cause_mode']}\n")
    fr12(api, None)
    fr13(api, me, a.save)
    failed = [fr for fr, ok in RESULTS if not ok]
    print("\n" + ("All checks pass." if not failed else f"Failing: {sorted(set(failed))}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
