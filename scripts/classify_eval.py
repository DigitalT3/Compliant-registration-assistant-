"""FR-09 check: type and top-3 root-cause suggestion, each with a one-line reason, in 3 seconds or less.

    python -m scripts.classify_eval --url http://127.0.0.1:8001 --email you@example.nl [--runs 3]

Signs in with a real account (hidden password prompt, or CHECK_PASSWORD) and calls the endpoints the screen uses:
/api/complaints/classify (the suggestion: what the employee waits for when leaving Describe) and /api/complaints/summarise
(the summary, which the screen writes alongside and shows right behind the suggestion). For the ten typical complaints, --runs times each, it reports the time (median, 95th
percentile, slowest, share within 3 s) and checks: a complaint type from the configured list, three
different causes from the root-cause list, each with a one-line reason, best first. It also reports how often a cause the
project's reviewer accepts (expected_causes in summary_cases.json) is among the three. Calls the configured model
10 x runs x 2 times (synthetic text only).
"""
import argparse
import getpass
import json
import math
import os
import statistics
import sys
from pathlib import Path

from scripts.requirements_check import Api
from scripts.summary_eval import SITES

ROOT = Path(__file__).resolve().parents[1]
LIMIT_S = 3.0


def structure_problems(result, cause_ids, type_ids, need=3):
    """Problems with one suggestion. ``need`` = the number of candidates required (3 for the live model; None allows 1 to 3)."""
    bad = []
    cls = result.get("classification", result)
    if cls.get("complaint_type") not in type_ids:
        bad.append(f"type {cls.get('complaint_type')!r} is not in the list")
    cands = cls.get("candidates") or []
    if (len(cands) != need) if need else not 1 <= len(cands) <= 3:
        bad.append(f"{len(cands)} candidates, expected {need or '1 to 3'}")
    ids = [c.get("root_cause_id") for c in cands]
    if len(set(ids)) != len(ids):
        bad.append("a cause is suggested twice")
    for c in cands:
        if c.get("root_cause_id") not in cause_ids:
            bad.append(f"cause {c.get('root_cause_id')!r} is not in the list")
        r = (c.get("reason") or "").strip()
        if not r or "\n" in r or len(r) > 200:
            bad.append(f"reason for {c.get('root_cause_id')} is not a one-liner ({len(r)} chars)")
    if [c.get("confidence") for c in cands] != sorted((c.get("confidence") for c in cands), reverse=True):
        bad.append("not best first")
    return bad


def pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    ap.add_argument("--runs", type=int, default=3)
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
    cfg, _ = api.call("GET", "/api/config")
    causes = {c["id"] for c in api.call("GET", "/api/config/root-causes")[0]["root_causes"]}
    types = {t["id"] for t in cfg["types"]}
    print(f"AI provider {health.get('ai_provider')}{' (MOCK)' if health.get('ai_mock') else ''}, region {health.get('ai_region')}; signed in, demo mode off; {a.runs} runs per complaint\n")
    cases = json.loads((ROOT / "tests/acceptance/summary_cases.json").read_text(encoding="utf-8"))["cases"]
    times = {"classify": [], "summarise": []}
    problems, hits, type_ok, first_hits, n = [], 0, 0, 0, 0
    for c in cases:
        for _ in range(a.runs):
            out, dt = api.call("POST", "/api/complaints/classify", {"text": c["text"]})
            times["classify"].append(dt)
            if out.get("ai_status") != "ok":
                problems.append(f"{c['id']}: classify failed ({out.get('error_category')})")
                continue
            res = out["result"]
            problems += [f"{c['id']}: {p}" for p in structure_problems(res, causes, types)]
            top = [x["root_cause_id"] for x in res["candidates"]]
            n += 1
            hits += bool(set(top) & set(c["expected_causes"]))
            first_hits += top[:1] == [c["expected_causes"][0]] or (top[:1] and top[0] in c["expected_causes"])
            type_ok += res.get("complaint_type") in c["accept_types"]
            out2, dt2 = api.call("POST", "/api/complaints/summarise", {"text": c["text"], "complaint_type": c["type"], "site_id": SITES.get(c.get("site"))})
            times["summarise"].append(dt2)
            if out2.get("ai_status") != "ok":
                problems.append(f"{c['id']}: summarise failed ({out2.get('error_category')})")
    ok = True
    for name, label in (("classify", "suggestion (/classify)  "), ("summarise", "summary (/summarise)    ")):
        t = times[name]
        within = sum(x <= LIMIT_S for x in t)
        print(f"{label}: median {statistics.median(t):.1f}s · 95th pct {pct(t, 95):.1f}s · slowest {max(t):.1f}s · within {LIMIT_S:.0f}s: {within} of {len(t)}")
        if name == "classify":                                   # the limit applies to the suggestion
            ok &= within >= math.ceil(0.95 * len(t))
    print(f"\nstructure (type from list, 3 distinct causes from the list, one-line reason, best first): {'all sound' if not problems else f'{len(problems)} problems'}")
    for p in problems[:8]:
        print("   ", p)
    print(f"a cause the reviewer accepts is in the top 3: {hits} of {n} ({hits / max(n, 1):.0%}); first choice acceptable: {first_hits} of {n}; type as expected: {type_ok} of {n}")
    print("\n" + ("PASS: at least 95% of the suggestions within 3 s, all well-formed." if ok and not problems else "NOT MET: see above."))
    return 0 if ok and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
