"""Check FR-01 to FR-08 and FR-14 against a RUNNING app with a real account (no demo header), each at its acceptance criterion.

    python -m scripts.requirements_check --url http://127.0.0.1:8001 --email you@example.nl      # asks for the password (hidden)
    python -m scripts.requirements_check --url ... --email ... --save                            # also saves test complaints (FR-04 edits, FR-07 texts)
    ... --rater-email owner@example.nl                                                           # also checks the rating screen's data as a process owner (FR-08)

It signs in like the browser does (e-mail and password, bearer token). The account needs the employee role (or admin).
FR-02 calls the model the app is configured with, ten times (synthetic emails). Without --save nothing is written
except the usual AI-call log rows.
"""
import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list = []


class Api:
    def __init__(self, base):
        self.base, self.token = base.rstrip("/"), None

    def call(self, method, path, body=None, params=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + self.token} if self.token else {})})
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read() or b"{}")
            data["_status"] = e.code
        return data, time.perf_counter() - t


def report(fr, name, ok, detail):
    RESULTS.append((fr, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {fr} {name}: {detail}")


def fr01(api, customers):
    ok_n, worst, bad = 0, 0.0, []
    for c in customers:
        orders = api.call("GET", f"/api/customers/{c['id']}/context", params={"all": "true"})[0]["orders"]
        inputs = [("number", c["number"]), ("name", c["name"]), ("order", orders[0]["reference"]), ("container", orders[0]["container"])]
        for kind, q in inputs:
            res, dt = api.call("GET", "/api/customers/search", params={"q": q})
            worst = max(worst, dt)
            hit = any(x["customer_id"] == c["id"] for x in res.get("candidates", []))
            if hit and dt <= 2.0:
                ok_n += 1
            else:
                bad.append(f"{c['number']} {kind}: {'wrong customer' if not hit else f'{dt:.1f}s'}")
    total = len(customers) * 4
    report("FR-01", "four inputs find the customer in <= 2 s", ok_n == total, f"{ok_n} of {total} searches right and fast; slowest {worst:.2f}s" + (f"; {bad[:3]}" if bad else ""))


def fr02(api):
    cases = json.loads((ROOT / "tests/acceptance/email_cases.json").read_text(encoding="utf-8"))["cases"]
    right, detail = 0, []
    for k in cases:
        out, _ = api.call("POST", "/api/complaints/extract", {"text": k["text"]})
        q = (out.get("result") or {}).get("customer_query")
        found = api.call("GET", "/api/customers/search", params={"q": q})[0] if q else {"count": 0, "candidates": []}
        number = found["candidates"][0]["number"] if found["count"] == 1 else None
        right += number == k["expected"]
        if number != k["expected"]:
            detail.append(f"{k['id']} got {number}")
    report("FR-02", "pasted email finds the customer for >= 8 of 10", right >= 8, f"{right} of {len(cases)}" + (f" ({', '.join(detail)})" if detail else ""))


def fr03(api, customers):
    bad = []
    for c in customers:
        card = api.call("GET", "/api/customers/search", params={"q": c["number"]})[0]["candidates"][0]
        ctx = api.call("GET", f"/api/customers/{c['id']}/context", params={"all": "true"})[0]
        orders = sorted(ctx["orders"], key=lambda o: ((o["date"] or ""), o["id"]), reverse=True)[:10]
        if [s["id"] for s in card["sites"]] != [s["id"] for s in ctx["sites"]]:
            bad.append(f"{c['number']} sites")
        if {k["reference"] for k in card["contracts"] if k["active"]} != {k["reference"] for k in ctx["contracts"] if k["active"]}:
            bad.append(f"{c['number']} contracts")
        if [(o["reference"], o["container"], o["status"]) for o in card["recent_orders"]] != [(o["reference"], o["container"], o["status"]) for o in orders]:
            bad.append(f"{c['number']} orders")
    report("FR-03", "sites, active contracts, last 10 orders match the data", not bad, f"{len(customers) - len({b.split()[0] for b in bad})} of {len(customers)} customers exact" + (f"; {bad[:3]}" if bad else ""))


def today_nl():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat()
    except Exception:
        return date.today().isoformat()


def fr04(api, customers, me, save):
    fields = ("customer_id", "site_id", "contract_id", "order_id", "container", "channel", "registration_date", "registering_user")
    blanks = []
    for c in customers:
        card = api.call("GET", "/api/customers/search", params={"q": c["number"]})[0]["candidates"][0]
        f = api.call("POST", "/api/prefill", {"customer_id": card["customer_id"], "site_id": card["matched_site_id"],
                                              "order_id": card["matched_order_id"], "origin": "search", "guess_site": True})[0]["fields"]
        blanks += [f"{c['number']}:{k}" for k in fields if not f.get(k, {}).get("value")]
        if f["registering_user"]["value"] != me["id"] or f["registration_date"]["value"] != today_nl():
            blanks.append(f"{c['number']}:user/date")
    report("FR-04", "all prefillable fields filled after a match", not blanks, f"{len(customers)} customers" + (f"; blank: {blanks[:4]}" if blanks else "; none blank"))
    if not save:
        print("  [skip] FR-04 edits saved: run with --save to save one test complaint with every field edited")
        return
    c = customers[0]
    ctx = api.call("GET", f"/api/customers/{c['id']}/context", params={"all": "true"})[0]
    other_site = next(s["id"] for s in ctx["sites"] if s["id"] != ctx["sites"][0]["id"])
    contract = next(k["id"] for k in ctx["contracts"] if k["site_id"] == other_site)
    order = next(o for o in ctx["orders"] if o["site_id"] == other_site)
    colleagues = api.call("GET", "/api/users/colleagues")[0]["items"]
    mate = next((x for x in colleagues if x["id"] != me["id"]), None)
    day = (date.fromisoformat(today_nl()) - timedelta(days=1)).isoformat()
    body = {"customer_id": c["id"], "site_id": other_site, "contract_id": contract, "order_id": order["id"], "channel": "email",
            "complaint_type": "service", "root_cause": "other", "other_reason": "requirements check", "description": "Requirements check complaint (synthetic).",
            "registration_date": day, **({"registering_user": mate["id"]} if mate else {})}
    saved, _ = api.call("POST", "/api/complaints", body)
    rec = api.call("GET", f"/api/complaints/{saved.get('id')}")[0] if saved.get("id") else {}
    ok = bool(rec) and (rec["site_id"], rec["contract_id"], rec["order_id"], rec["channel"], rec["registration_date"]) == (other_site, contract, order["id"], "email", day) \
        and (not mate or rec["registering_user"] == mate["id"])
    report("FR-04", "each field can be edited and the edit is saved", ok, f"saved {saved.get('id')}: site, contract, order, channel, date" + (", registering user" if mate else " (no colleague to test the user)") + " changed")


def fr05(api, customers):
    cfg = api.call("GET", "/api/config")[0]
    doc = (ROOT / "docs/DEFAULTS.md").read_text(encoding="utf-8")
    card = api.call("GET", "/api/customers/search", params={"q": customers[0]["number"]})[0]["candidates"][0]
    wrong = []
    for t in cfg["types"]:
        want = {**cfg["defaults"].get("_all", {}), **cfg["defaults"].get(t["id"], {})}
        f = api.call("POST", "/api/prefill", {"customer_id": card["customer_id"], "complaint_type": t["id"], "origin": "search", "guess_site": True})[0]["fields"]
        for k in ("priority", "status", "owner_team", "response_target_days"):
            if f[k]["value"] != want[k]:
                wrong.append(f"{t['id']}.{k}")
        if t["id"] not in doc or str(want["response_target_days"]) not in doc:
            wrong.append(f"{t['id']} not in docs/DEFAULTS.md")
    report("FR-05", "defaults documented per type and applied on type selection", not wrong, f"{len(cfg['types'])} types" + (f"; wrong: {wrong}" if wrong else "; all applied and documented"))


def fr07(api, me, save):
    if not save:
        print("  [skip] FR-07 stored as typed: run with --save (it saves 8 test complaints)")
        return
    cases = json.loads((ROOT / "tests/acceptance/description_cases.json").read_text(encoding="utf-8"))["cases"]
    card = api.call("GET", "/api/customers/search", params={"q": "100009"})[0]["candidates"][0]
    bad = []
    for c in cases:
        saved, _ = api.call("POST", "/api/complaints", {"customer_id": card["customer_id"], "site_id": card["sites"][0]["id"], "channel": "phone",
                            "complaint_type": "service", "root_cause": "missed", "description": c["text"], "language": c["language"]})
        rec = api.call("GET", f"/api/complaints/{saved.get('id')}")[0] if saved.get("id") else {}
        if rec.get("original_text") != c["text"] or rec.get("language") != c["language"]:
            bad.append(c["name"])
    long_refused = api.call("POST", "/api/complaints", {"customer_id": card["customer_id"], "channel": "phone", "complaint_type": "service",
                            "root_cause": "missed", "description": "x" * 8001, "language": "en"})[0].get("_status")
    report("FR-07", "Dutch and English stored exactly as typed", not bad and long_refused == 422,
           f"{len(cases) - len(bad)} of {len(cases)} identical; 8001 characters -> {long_refused}" + (f"; differing: {bad}" if bad else ""))


def fr08(api, rater):
    from scripts.summary_eval import SITES, check
    cases = json.loads((ROOT / "tests/acceptance/summary_cases.json").read_text(encoding="utf-8"))["cases"]
    bad = []
    for c in cases:
        out, _ = api.call("POST", "/api/complaints/analyze", {"text": c["text"], "complaint_type": c["type"], "site_id": SITES.get(c.get("site")), "container": c.get("container")})
        bad += [f"{c['id']}: {p}" for p in check(c, out)]
    report("FR-08", "structured summary from the template (what/where/when/impact + type fields), nothing invented", not bad,
           f"{len(cases) - len({b.split(':')[0] for b in bad})} of {len(cases)} sound" + (f"; {bad[:3]}" if bad else ""))
    if not rater:
        print("  [skip] FR-08 rating screen data: run with --rater-email (and CHECK_RATER_PASSWORD) to check it as a process owner")
        return
    sample, _ = rater.call("GET", "/api/evaluations/sample", params={"limit": 10})
    items = sample.get("items", [])
    shape = bool(items) and all({"what", "where", "when", "impact", "extras"} <= set(i["summary"] or {}) for i in items if i["summary"]) \
        and not any(k in items[0] for k in ("root_cause", "complaint_type"))
    no_vote, _ = rater.call("POST", "/api/evaluations", {"complaint_id": items[0]["id"]}) if items else ({}, 0)
    report("FR-08", "process owner sees the labelled summary, blind; a rating needs an explicit choice", shape and no_vote.get("_status") == 422,
           f"{len(items)} complaints to rate; empty rating refused ({no_vote.get('_status')}); no rating was written")


def fr14(api, me, save):
    mapping, _ = api.call("GET", "/api/field-mapping")
    names = [f["target_field"] for f in mapping.get("fields", [])]
    listing, _ = api.call("GET", "/api/complaints", params={"page_size": 100, "include_seed": "true"})
    ids = [c["id"] for c in listing.get("items", [])]
    short = []
    for cid in ids:
        t, _ = api.call("GET", f"/api/complaints/{cid}/target")
        if list(t.get("record", {})) != names or t.get("missing_required"):
            short.append(cid)
    report("FR-14", "the field list is one-to-one with what is stored", mapping.get("one_to_one") is True and not mapping.get("problems"),
           f"{len(names)} target fields + {len(mapping.get('not_mapped', {}))} columns excluded with a reason = {len(names) + len(mapping.get('not_mapped', {}))} stored columns; validated against the complaint system: {mapping.get('validated')}")
    report("FR-14", "every complaint maps to exactly those fields with the required ones filled", not short,
           f"{len(ids) - len(short)} of {len(ids)} complaints" + (f"; not: {short[:5]}" if short else ""))
    if not save:
        print("  [skip] FR-14 saved values arrive as entered: run with --save (saves 1 test complaint)")
        return
    card = api.call("GET", "/api/customers/search", params={"q": "100009"})[0]["candidates"][0]
    text = "Café 'De Ruiter' – €45,50 te veel gefactureerd.\r\nTweede regel  "
    saved, _ = api.call("POST", "/api/complaints", {"customer_id": card["customer_id"], "site_id": "C009-S1", "contract_id": "C009-K1", "order_id": "C009-O10",
                        "channel": "email", "complaint_type": "billing", "root_cause": "other", "other_reason": "Seagull nest under the lid",
                        "language": "nl", "priority": "high", "description": text})
    t, _ = api.call("GET", f"/api/complaints/{saved.get('id')}/target") if saved.get("id") else ({}, 0)
    r = t.get("record", {})
    want = {"PROVISIONAL_ComplaintId": saved.get("id"), "PROVISIONAL_Account": card["customer_id"], "PROVISIONAL_Site": "C009-S1", "PROVISIONAL_Contract": "C009-K1",
            "PROVISIONAL_Order": "C009-O10", "PROVISIONAL_Container": "BOX-009-1", "PROVISIONAL_Channel": "email", "PROVISIONAL_RegisteredBy": me["id"],
            "PROVISIONAL_Status": "open", "PROVISIONAL_Priority": "high", "PROVISIONAL_Description": text, "PROVISIONAL_Language": "nl",
            "PROVISIONAL_Type": "billing", "PROVISIONAL_RootCause": "other", "PROVISIONAL_OtherReason": "Seagull nest under the lid"}
    wrong = [k for k, v in want.items() if r.get(k) != v]
    report("FR-14", "a saved record arrives in the target fields exactly as entered", not wrong and not t.get("missing_required") and list(r) == names,
           f"{saved.get('id')}: {len(want)} values compared" + (f"; differing: {wrong}" if wrong else ", all identical"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--rater-email", help="a process owner (evaluator) account to check the rating screen data")
    a = ap.parse_args()
    api = Api(a.url)
    health, _ = api.call("GET", "/health")
    print(f"App {a.url}: AI provider {health.get('ai_provider')}{' (MOCK)' if health.get('ai_mock') else ''}")
    demo, _ = api.call("GET", "/api/auth/me")                 # no header, no token: a real-mode app answers 401
    if demo.get("_status") != 401:
        print("The app answered without sign-in: it is not in real mode. Stopping.")
        return 2
    pw = os.environ.get("CHECK_PASSWORD") or getpass.getpass(f"Password for {a.email}: ")
    login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": pw})
    if not login.get("token") or login.get("must_change_password"):
        print("Sign-in failed or a password change is pending: sign in once in the browser first.")
        return 2
    api.token = login["token"]
    me, _ = api.call("GET", "/api/auth/me")
    print(f"Signed in as {me['name']} ({me['role']}), demo mode off\n")
    listing, _ = api.call("GET", "/api/customers", params={"limit": 200}) if "customer_data" in me["permissions"] else ({"items": []}, 0)
    customers = [c for c in listing.get("items", []) if c.get("source") == "seed"][: a.n]
    if len(customers) < a.n:
        print(f"Only {len(customers)} seeded customers visible (need {a.n}); the account needs customer_data.")
        return 2
    rater = None
    if a.rater_email:
        rater = Api(a.url)
        rl, _ = rater.call("POST", "/api/auth/login", {"email": a.rater_email, "password": os.environ.get("CHECK_RATER_PASSWORD") or getpass.getpass(f"Password for {a.rater_email}: ")})
        if not rl.get("token"):
            print("Rater sign-in failed (a pending password change must be done in the browser first).")
            return 2
        rater.token = rl["token"]
    fr01(api, customers); fr02(api); fr03(api, customers); fr04(api, customers, me, a.save); fr05(api, customers)
    fr07(api, me, a.save); fr08(api, rater); fr14(api, me, a.save)
    failed = [fr for fr, ok in RESULTS if not ok]
    print("\n" + ("All checks pass." if not failed else f"Failing: {sorted(set(failed))}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
