"""FR-08 check: do the ten typical complaints (tests/acceptance/summary_cases.json) get a sound structured summary?

    python -m scripts.summary_eval --url http://127.0.0.1:8001 --email you@example.nl [--out summaries.csv]

Signs in with a real account (hidden password prompt, or CHECK_PASSWORD), calls the same endpoint the screen uses and
checks what a program can check: the summary is in the language of the text, the fields the text states are filled, the
fields it does not state stay empty, the type-specific fields hold the invoice/amount/container/vehicle, and no number
appears that the text did not contain. Whether a summary is USABLE is the process owners' judgement: --out writes a
sheet with the text, the summary and an empty "usable" column for them to fill in. Calls the configured model 10 times
(synthetic text only).
"""
import argparse
import csv
import getpass
import json
import os
import re
import sys
from pathlib import Path

from scripts.requirements_check import Api

ROOT = Path(__file__).resolve().parents[1]
SITES = {"Synthetic depot 1": "C009-S1", "Synthetic depot 2": "C009-S2"}
FIELDS = ("what", "where", "when", "impact")


def digits(text: str) -> set:
    return set(re.findall(r"\d[\d.,:-]*\d|\d", text or ""))


def check(case, out):
    """Return the list of problems (empty = the summary is structurally sound)."""
    if out.get("ai_status") != "ok":
        return [f"AI call failed: {out.get('error_category')}"]
    s = out["result"]["summary"]
    bad = []
    if s["language"] != case["language"]:
        bad.append(f"language {s['language']}, text is {case['language']}")
    for f in case["present"]:
        if not (s.get(f) or "").strip():
            bad.append(f"'{f}' is stated in the text but empty")
    for f in case["absent"]:
        if (s.get(f) or "").strip():
            bad.append(f"'{f}' is not in the text but filled: {s[f]!r}")
    for k, want in case.get("extras", {}).items():
        got = (s.get("extras") or {}).get(k) or ""
        if want.lower() not in got.lower() and want.replace(",", ".") not in got:
            bad.append(f"extra {k}: expected '{want}', got {got!r}")
    known = digits(case["text"]) | digits(case.get("container", "")) | {c for c in re.findall(r"\d+", case.get("site", ""))}
    shown = " ".join([(s.get(f) or "") for f in FIELDS] + [v or "" for v in (s.get("extras") or {}).values()])
    invented = {d for d in digits(shown) if d not in known and not any(d in k or k in d for k in known)}
    if invented:
        bad.append(f"numbers not in the text: {sorted(invented)}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    api = Api(a.url)
    health, _ = api.call("GET", "/health")
    if api.call("GET", "/api/auth/me")[0].get("_status") != 401:
        print("The app answered without sign-in: not in real mode. Stopping.")
        return 2
    login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": os.environ.get("CHECK_PASSWORD") or getpass.getpass("Password: ")})
    if not login.get("token") or login.get("must_change_password"):
        print("Sign-in failed or a password change is pending.")
        return 2
    api.token = login["token"]
    print(f"AI provider {health.get('ai_provider')}{' (MOCK)' if health.get('ai_mock') else ''}; signed in, demo mode off\n")
    cases = json.loads((ROOT / "tests/acceptance/summary_cases.json").read_text(encoding="utf-8"))["cases"]
    sound, rows = 0, []
    for c in cases:
        out, dt = api.call("POST", "/api/complaints/analyze", {"text": c["text"], "complaint_type": c["type"], "site_id": SITES.get(c.get("site")), "container": c.get("container")})
        problems = check(c, out)
        sound += not problems
        s = (out.get("result") or {}).get("summary", {})
        print(f"{c['id']} {c['type']:8} {c['language']}  {dt:4.1f}s  {'OK ' if not problems else 'FIX'}  {'; '.join(problems)}")
        rows.append([c["id"], c["type"], c["language"], c["text"]] + [s.get(f) or "" for f in FIELDS]
                    + ["; ".join(f"{k}: {v}" for k, v in (s.get("extras") or {}).items() if v), ""])
    print(f"\n{sound} of {len(cases)} summaries structurally sound (the usable rating is for the process owners)")
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "type", "language", "complaint text", "what", "where", "when", "impact", "type-specific fields", "usable (yes/no)"])
            w.writerows(rows)
        print(f"Review sheet written: {a.out}")
    return 0 if sound == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
