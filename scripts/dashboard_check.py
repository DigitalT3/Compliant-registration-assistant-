"""FR-17 check: are the dashboard's numbers the numbers in the log?

    python -m scripts.dashboard_check --url http://127.0.0.1:8001 --email <administrator>
    python -m scripts.dashboard_check --direct                       # no sign-in: the app's own code on the configured database

Signs in with a real administrator account (hidden password prompt, or CHECK_PASSWORD), reads the dashboard (overall and by user
group) and recomputes every figure straight from the raw tables (sessions, step_events, field_events, ai_events, complaints) with its
own code, then compares. It reads the database the app is configured for (POC_DB / DATABASE_URL), so run it where the app runs.
Figures: time per registration, the "Other" share, suggestion acceptance (first cause kept, cause within the top 3, summary kept,
type kept) and the repeat rate, overall and by user group. Read-only.
"""
import argparse
import getpass
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

from backend import db
from backend.settings import get_config
from scripts.requirements_check import Api

LEGACY = {"check_repeats": "repeat_save", "review_save": "repeat_save"}      # two steps that were merged: older registrations used the old names

CLOSE = 0.01


def raw(conn):
    """The figures, from the tables, by the definitions on the dashboard (not by the dashboard's code)."""
    cap = get_config()["metrics"].get("step_idle_cap_seconds") or 10 ** 9
    rows = [dict(r) for r in conn.execute(
        "SELECT s.id, s.user_group g, s.started, s.ended, s.status, c.root_cause, c.repeat_detected FROM sessions s LEFT JOIN complaints c ON c.session_id=s.id")]
    saved = [r for r in rows if r["status"] == "saved"]
    for r in saved:                                              # time per registration: the visits to the steps added up, each visit at most the cap
        total, open_at, step = 0.0, None, None
        for e in conn.execute("SELECT step, event_type, at FROM step_events WHERE session_id=? ORDER BY id", (r["id"],)).fetchall():
            at = datetime.fromisoformat(e["at"])
            if e["event_type"] == "step_entered":
                if open_at is not None:                           # entered the next step without a completion: the visit ends here
                    total += min((at - open_at).total_seconds(), cap)
                open_at, step = at, LEGACY.get(e["step"], e["step"])
            elif e["event_type"] == "step_completed" and open_at is not None and LEGACY.get(e["step"], e["step"]) == step:
                total += min((at - open_at).total_seconds(), cap)  # the visit ends when the step is completed
                open_at = None
        if open_at is not None and r["ended"]:
            total += min((datetime.fromisoformat(r["ended"]) - open_at).total_seconds(), cap)
        r["seconds"] = total
    final, top3 = {}, {}
    for e in conn.execute("SELECT session_id, field, origin FROM field_events WHERE event_type='final'"):
        final[(e["session_id"], e["field"])] = e["origin"]
    for e in conn.execute("SELECT session_id, in_top3 FROM ai_events WHERE operation='classification_outcome' AND in_top3 IS NOT NULL"):
        top3[e["session_id"]] = e["in_top3"]

    def block(rs):
        def kept(field):
            o = [final[(r["id"], field)] for r in rs if final.get((r["id"], field)) in ("suggested", "edited")]
            return (sum(x == "suggested" for x in o) / len(o) if o else None, len(o))
        t = [top3[r["id"]] for r in rs if r["id"] in top3]
        secs = [r["seconds"] for r in rs]
        return {"seconds_mean": statistics.mean(secs) if secs else None, "seconds_median": statistics.median(secs) if secs else None, "n_time": len(secs),
                "other": (sum(r["root_cause"] == "other" for r in rs) / len(rs) if rs else None, len(rs)),
                "repeat": (sum(bool(r["repeat_detected"]) for r in rs) / len(rs) if rs else None, len(rs)),
                "cause_first": kept("root_cause"), "top3": (sum(t) / len(t) if t else None, len(t)), "summary_kept": kept("summary"), "type_kept": kept("complaint_type")}
    groups = defaultdict(list)
    for r in saved:
        groups[r["g"] or "none"].append(r)
    return block(saved), {k: block(v) for k, v in groups.items()}, {"started": len(rows), "saved": len(saved)}


def close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= CLOSE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email")
    ap.add_argument("--direct", action="store_true", help="no sign-in: compute the dashboard figures with the app's own code on the configured database")
    a = ap.parse_args()
    if a.direct:
        from backend.services import metrics
        with db.connect() as conn:
            dash = metrics.summary(conn, {"group_by": "group"})
    else:
        if not a.email:
            print("--email is required unless --direct is used")
            return 2
        api = Api(a.url)
        login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": os.environ.get("CHECK_PASSWORD") or getpass.getpass("Password: ")})
        if not login.get("token") or login.get("must_change_password"):
            print("Sign-in failed or a password change is pending.")
            return 2
        api.token = login["token"]
        dash, _ = api.call("GET", "/api/analytics/summary", params={"group_by": "group"})
    if dash.get("empty"):
        print("The dashboard is empty: no registrations recorded yet.")
        return 1
    with db.connect() as conn:
        total, groups, counts = raw(conn)
    checks = []

    def compare(label, shown, mine):
        ok = close(shown, mine)
        checks.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: dashboard {shown if shown is None else round(shown, 3)} | log {mine if mine is None else round(mine, 3)}")

    print(f"Registrations: dashboard started {dash['sessions']['started']} saved {dash['sessions']['saved']} | log started {counts['started']} saved {counts['saved']}")
    checks += [dash["sessions"]["started"] == counts["started"], dash["sessions"]["saved"] == counts["saved"]]

    def figures(label, d, acc, mine, oth, rep, dur_mean, dur_median, dur_n):
        compare(f"{label} time per registration, mean (s)", dur_mean, mine["seconds_mean"])
        if dur_median != "skip":                                  # the group table shows the mean only
            compare(f"{label} time per registration, median (s)", dur_median, mine["seconds_median"])
        checks.append(dur_n == mine["n_time"])
        compare(f"{label} 'Other' share", oth["value"], mine["other"][0])
        compare(f"{label} repeat rate", rep["value"], mine["repeat"][0])
        for k in ("cause_first", "top3", "summary_kept", "type_kept"):
            compare(f"{label} acceptance, {k}", acc[k]["value"], mine[k][0])
            checks.append(acc[k]["n"] == mine[k][1])
    print("\nOverall")
    figures("overall", dash, dash["acceptance"], total, dash["classification"]["other_share"], dash["repeat"]["rate"],
            dash["duration_seconds"]["mean"], dash["duration_seconds"]["median"], dash["duration_seconds"]["n"])
    for k, g in dash.get("groups", {}).items():
        if k not in groups:
            checks.append(g["saved"] == 0)
            continue
        print(f"\nUser group: {k}")
        figures(k, g, g["acceptance"], groups[k], g["other_share"], g["repeat_rate"], g["mean_duration"], "skip", g["n_duration"])
    print(f"\n{sum(checks)} of {len(checks)} figures agree with the log")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
