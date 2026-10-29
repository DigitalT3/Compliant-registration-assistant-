"""Go/no-go readout for the business owner (Glenn at Renewi).

The page brings the evidence together (targets with sample sizes, the baseline comparison) and the open conditions
(cause list agreed, repeat rule signed off, enough data). It does not compute a verdict: the business owner records
the decision, which is stored with the evidence it was based on. Decisions live in ``app_settings`` and in the audit log.
"""
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config
from . import metrics, rule_signoff, taxonomy_review

KEY = "go_no_go"
DECISIONS = ("go", "conditional", "no_go")


def _load(conn) -> list:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (KEY,)).fetchone()
    return json.loads(row[0]) if row else []


def _count(conn, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


# PUBLIC_INTERFACE
def evidence(conn) -> dict:
    """The evidence and the open conditions as they are now."""
    cfg = get_config()
    summ = metrics.summary(conn, {})
    cause, rule = taxonomy_review.status(conn, cfg), rule_signoff.status(conn, cfg)
    saved = _count(conn, "SELECT count(*) FROM sessions WHERE status='saved'")
    labels = _count(conn, "SELECT count(*) FROM evaluations WHERE expert_cause IS NOT NULL")
    interviews = _count(conn, "SELECT count(*) FROM exit_interviews")
    small = cfg["targets"]["small_sample_below"]
    conditions = [
        {"id": "cause_list", "ok": cause["state"] == "agreed", "detail": f"{cause['state']}: {cause['agreed']} of {cause['required']} agreed"},
        {"id": "repeat_rule", "ok": rule["state"] == "signed_off", "detail": f"{rule['state']} ({rule['rule_version']})"},
        {"id": "sessions", "ok": saved >= small, "detail": f"{saved} saved registrations (at least {small})"},
        {"id": "labels", "ok": labels >= small, "detail": f"{labels} expert labels (at least {small})"},
        {"id": "interviews", "ok": interviews >= small, "detail": f"{interviews} exit interviews (at least {small})"},
        {"id": "baseline", "ok": bool(summ.get("duration_seconds", {}).get("baseline_seconds")) if not summ.get("empty") else False,
         "detail": "timed baseline recorded" if not summ.get("empty") and summ.get("duration_seconds", {}).get("baseline_seconds") else "no timed baseline yet"},
    ]
    dur = summ.get("duration_seconds") or {}
    return {"empty": bool(summ.get("empty")), "targets": summ.get("targets", []) if not summ.get("empty") else [],
            "baseline": {k: dur.get(k) for k in ("mean", "n", "baseline_seconds", "baseline_n", "faster_than_baseline")},
            "conditions": conditions, "cause_list": cause["state"], "repeat_rule": rule["state"],
            "decisions": sorted(_load(conn), key=lambda d: d["at"], reverse=True)}


# PUBLIC_INTERFACE
def decide(conn, user: dict, decision: str, comment: str | None) -> dict:
    """Record the go/no-go decision with the evidence snapshot it rests on."""
    if decision not in DECISIONS:
        raise ApiError(422, "invalid_decision", "decision must be go, conditional or no_go.")
    comment = (comment or "").strip()
    if not comment:
        raise ApiError(422, "comment_required", "Give the reason for the decision.")
    ev = evidence(conn)
    entry = {"user_id": user["id"], "name": user["name"], "decision": decision, "comment": comment[:1000], "at": db.now(),
             "targets": [{k: t[k] for k in ("id", "status", "value", "n")} for t in ev["targets"]],
             "conditions": [{k: c[k] for k in ("id", "ok")} for c in ev["conditions"]]}
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (KEY, json.dumps(_load(conn) + [entry], ensure_ascii=False)))
    audit(conn, user["id"], "go_no_go_decision", {"decision": decision, "comment": entry["comment"]})
    conn.commit()
    return evidence(conn)


# PUBLIC_INTERFACE
def csv_rows(ev: dict) -> list:
    """Rows for the export: targets, then conditions, then the recorded decisions."""
    return ([["target", t["target"], t["value"], t["n"], t["status"]] for t in ev["targets"]]
            + [["condition", c["id"], "", c["ok"], c["detail"]] for c in ev["conditions"]]
            + [["decision", d["name"], d["decision"], d["at"], d["comment"]] for d in ev["decisions"]])
