"""Read-only reporting feed for Power BI (FR-17 and the "Report" step of the user flow).

Flat tables for the dashboard measures: time per registration, the "Other" share, suggestion acceptance and the repeat rate by user
group, plus the sessions, suggestions, employees, baseline, exit interviews and ratings behind them. Power BI reads them with the
Web connector and a reporting key (``REPORTING_TOKEN`` in ``.env``, sent as the ``X-Reporting-Key`` header); a signed-in person with
the analytics permission can read them too (a team lead sees their own team only). Nothing here writes to the PoC data.
"""
import hmac
import os
import re

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from .. import db
from ..auth import current_user
from ..dbutil import audit, connection
from ..errors import ApiError
from ..services import metrics, scope, sessions as sessions_svc
from ..settings import get_config
from . import testing

router = APIRouter(tags=["reporting"])

KEY_USER = {"id": "reporting-key", "name": "Power BI (reporting key)", "role": "admin"}
DATASETS = ("group_summary", "sessions", "suggestions", "employees", "baseline", "interviews", "ratings")


def reporting_user(request: Request, x_reporting_key: str | None = Header(default=None)) -> dict:
    """The reporting key (all teams, read-only) or a signed-in person with the analytics permission."""
    if x_reporting_key is not None:
        token = os.environ.get("REPORTING_TOKEN", "")
        if token and hmac.compare_digest(x_reporting_key.encode(), token.encode()):
            return KEY_USER
        raise ApiError(401, "invalid_reporting_key", "The reporting key is missing or wrong.")
    user = current_user(request, request.headers.get("authorization"), request.headers.get("x-demo-user"))
    if "analytics" not in get_config()["roles"].get(user["role"], []):
        raise ApiError(403, "forbidden", f"Role '{user['role']}' lacks the 'analytics' permission.")
    return user


def _pair(rate: dict | None):
    return (rate or {}).get("value"), (rate or {}).get("n")


def _summary_row(name: str, mean, n, other, repeat, acc, sessions=None, saved=None) -> dict:
    row = {"group": name, "sessions": sessions, "saved": saved, "mean_duration_s": mean, "duration_n": n}
    for label, rate in (("other_share", other), ("repeat_rate", repeat), ("first_cause_kept", (acc or {}).get("cause_first")),
                        ("top3_accepted", (acc or {}).get("top3")), ("summary_kept", (acc or {}).get("summary_kept")),
                        ("type_kept", (acc or {}).get("type_kept"))):
        row[label], row[label + "_n"] = _pair(rate)
    return row


def _group_summary(conn, user: dict) -> list:
    out = metrics.summary(conn, scope.scoped(user, {"group_by": "group"}))
    if out.get("empty"):
        return []
    rows = []
    cls, dur = out["classification"], out["duration_seconds"]
    rows.append(_summary_row("All groups" if not scope.lead_team(user) else scope.lead_team(user), dur["mean"], dur["n"], cls["other_share"],
                             out["repeat"]["rate"], out["acceptance"], out["sessions"]["started"], out["sessions"].get("saved")))
    for g, v in (out.get("groups") or {}).items():
        rows.append(_summary_row(g, v["mean_duration"], v["n_duration"], v["other_share"], v["repeat_rate"], v["acceptance"], v["sessions"], v["saved"]))
    return rows


def _dataset(conn, name: str, user: dict, mode: str | None, group: str | None) -> tuple:
    f = scope.scoped(user, {"mode": mode, "group": group})
    steps = sessions_svc.STEPS
    if name == "group_summary":
        rows = _group_summary(conn, user)
        return (list(rows[0]) if rows else ["group"]), [list(r.values()) for r in rows]
    if name == "sessions":
        items = metrics.session_list(conn, f, 1, 100000)["items"]
        return (["session_id", "user", "group", "mode", "participant", "scenario", "status", "duration_s", "root_cause", "repeat", "failure",
                 "first_field_s", "first_entry_s"] + [f"{s}_s" for s in steps],
                [[i["id"], i["actor"], i["user_group"], i["mode"], i["participant_id"], i["scenario"], i["status"], i["duration_seconds"],
                  i["root_cause"], i["repeat_detected"], i["failure_status"], i["first_field_seconds"], i["first_entry_seconds"]]
                 + [i["step_seconds"].get(s) for s in steps] for i in items])
    if name == "suggestions":
        items = metrics.suggestion_rows(conn, f)
        return (["complaint_id", "session_id", "team", "user", "mode", "saved_at", "field", "origin", "outcome"],
                [[i["complaint_id"], i["session_id"], i["team"], i["actor"], i["mode"], i["saved_at"], i["field"], i["origin"], i["outcome"]] for i in items])
    if name == "employees":
        data = metrics.employee_breakdown(conn, f)
        cols = ["employee", "team", "started", "saved", "abandoned", "median_s", "min_s", "max_s", "summary_accepted", "cause_accepted", "top3",
                "other_share", "prefill_rate", "repeat_rate", "enough_data"]
        line = lambda who, team, b: [who, team, b["started"], b["saved"], b["abandoned"], b["median_seconds"], b["min_seconds"], b["max_seconds"],
                                     b["summary_accepted"]["value"], b["cause_accepted"]["value"], b["top3"]["value"], b["other_share"]["value"],
                                     b["prefill_rate"]["value"], b["repeat_rate"]["value"], int(b["enough_data"])]
        rows = ([line("Team", "", data["team"])] if data["team"] else []) + [line(e["employee"], e["team"], e) for e in data["employees"]]
        return cols, rows
    scope.not_for_leads(user)                                  # the user-test tables are not split by team
    if name == "baseline":
        r = conn.execute("SELECT user_group, scenario, participant_id, seconds, note, at FROM baseline ORDER BY id").fetchall()
        return ["group", "scenario", "participant", "seconds", "note", "recorded_at"], [list(x) for x in r]
    if name == "interviews":
        r = conn.execute("SELECT participant_id, would_use_daily, comment, at FROM exit_interviews ORDER BY id").fetchall()
        return ["participant", "would_use_daily", "comment", "recorded_at"], [list(x) for x in r]
    r = conn.execute("SELECT e.complaint_id, e.usable, e.expert_cause, c.root_cause AS saved_cause, u.name AS rater, e.at FROM evaluations e "
                     "JOIN complaints c ON c.id=e.complaint_id LEFT JOIN users u ON u.id=e.actor "
                     "WHERE e.id IN (SELECT max(id) FROM evaluations GROUP BY complaint_id, actor) ORDER BY e.id").fetchall()
    return ["complaint_id", "usable", "expert_cause", "saved_cause", "rater", "rated_at"], [list(x) for x in r]


@router.get("/api/reporting/{dataset}", summary="Read-only dashboard tables for Power BI")
def reporting(dataset: str, format: str = Query("csv", pattern="^(csv|json)$"), mode: str | None = Query(None, pattern="^(assistant|plain)$"),
              group: str | None = None, user: dict = Depends(reporting_user)):
    """``group_summary`` (the FR-17 measures by user group), ``sessions``, ``suggestions``, ``employees``, ``baseline``, ``interviews`` or ``ratings``.

    CSV by default (the Power BI Web connector reads it directly); ``format=json`` returns ``{"columns": [...], "rows": [...]}``.
    """
    if not re.fullmatch(r"[a-z_]+", dataset) or dataset not in DATASETS:
        raise ApiError(404, "unknown_dataset", "Choose one of: " + ", ".join(DATASETS) + ".")
    with connection() as conn:
        columns, rows = _dataset(conn, dataset, user, mode, group)
        audit(conn, user["id"], "reporting_read", {"dataset": dataset, "rows": len(rows)})
        conn.commit()
    if format == "json":
        return JSONResponse({"dataset": dataset, "columns": columns, "rows": rows})
    return testing._csv(columns, rows, f"{dataset}.csv")
