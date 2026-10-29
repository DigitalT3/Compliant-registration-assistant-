"""Support for the timed user test: baseline timings, exit interviews, blind labelling sample, CSV exports."""
import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import db
from ..auth import require
from ..dbutil import audit, connection
from ..services import metrics, sessions as sessions_svc

router = APIRouter(tags=["user-test"])


class BaselineIn(BaseModel):
    """One stopwatch measurement on today's form (seconds from opening the form to saving)."""
    user_group: str = Field(..., min_length=1, max_length=60)
    scenario: str | None = Field(None, max_length=20)
    participant_id: str | None = Field(None, max_length=40)
    seconds: float = Field(..., gt=0, le=7200)
    note: str | None = Field(None, max_length=300)


class ExitIn(BaseModel):
    """Exit interview: would the participant use the assistant daily?"""
    participant_id: str = Field(..., min_length=1, max_length=40)
    would_use_daily: bool
    comment: str | None = Field(None, max_length=500)


@router.post("/api/baseline", status_code=201, summary="Record a stopwatch time on today's form")
def add_baseline(body: BaselineIn, user: dict = Depends(require("evaluate"))):
    """Store one baseline measurement; the dashboard compares PoC durations against these."""
    with connection() as conn:
        conn.execute("INSERT INTO baseline(user_group,scenario,participant_id,seconds,note,actor,at) VALUES(?,?,?,?,?,?,?)",
                     (body.user_group, body.scenario, body.participant_id, body.seconds, body.note, user["id"], db.now()))
        audit(conn, user["id"], "baseline_recorded", body.model_dump())
        conn.commit()
    return {"recorded": True}


@router.get("/api/baseline", summary="Baseline timings")
def list_baseline(user: dict = Depends(require("analytics"))):
    """All baseline rows with the mean per user group."""
    with connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM baseline ORDER BY id DESC")]
    by_group: dict = {}
    for r in rows:
        by_group.setdefault(r["user_group"], []).append(r["seconds"])
    return {"items": rows, "by_group": {g: {"mean_seconds": round(sum(v) / len(v), 2), "n": len(v)} for g, v in by_group.items()}}


@router.post("/api/exit-interviews", status_code=201, summary="Record an exit interview")
def add_exit(body: ExitIn, user: dict = Depends(require("evaluate"))):
    """Store whether the participant would use the assistant daily (PRD target: at least 5 of 6-8)."""
    with connection() as conn:
        conn.execute("INSERT INTO exit_interviews(participant_id,would_use_daily,comment,actor,at) VALUES(?,?,?,?,?)",
                     (body.participant_id, int(body.would_use_daily), body.comment, user["id"], db.now()))
        audit(conn, user["id"], "exit_interview_recorded", {"participant_id": body.participant_id})
        conn.commit()
    return {"recorded": True}


@router.get("/api/exit-interviews", summary="Exit interviews")
def list_exit(user: dict = Depends(require("analytics"))):
    """All exit interviews and the daily-use count."""
    with connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM exit_interviews ORDER BY id DESC")]
    return {"items": rows, "would_use_daily": {"yes": sum(r["would_use_daily"] for r in rows), "n": len(rows)}}


def _sample(conn, actor: str, limit: int) -> list:
    """Saved PoC complaints this rater has not labelled. The AI suggestion, type and saved cause are hidden."""
    rows = conn.execute(
        "SELECT c.id, c.language, c.original_text, c.summary_json FROM complaints c WHERE c.is_seed=0 AND c.id NOT IN "
        "(SELECT complaint_id FROM evaluations WHERE actor=? AND expert_cause IS NOT NULL) ORDER BY c.id LIMIT ?",
        (actor, limit)).fetchall()
    out = []
    for r in rows:
        summ = json.loads(r["summary_json"]) if r["summary_json"] else None
        out.append({"id": r["id"], "language": r["language"], "description": r["original_text"],
                    "summary": summ and {k: summ.get(k) for k in ("what", "where", "when", "impact")}})
    return out


@router.get("/api/evaluations/sample", summary="Blind labelling sample (cause and AI suggestion hidden)")
def label_sample(limit: int = Query(20, ge=1, le=200), user: dict = Depends(require("evaluate"))):
    """Complaints for blind expert labelling: the saved root cause is NOT included."""
    with connection() as conn:
        return {"items": _sample(conn, user["id"], limit)}


def _safe(v):
    """Neutralise spreadsheet formula injection in exported text cells."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _csv(header: list, rows: list, name: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows([[_safe(c) for c in r] for r in rows])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/api/export/sessions.csv", summary="Per-session timings as CSV")
def export_sessions(mode: str | None = Query(None, pattern="^(assistant|plain)$"), group: str | None = None,
                    user: dict = Depends(require("analytics"))):
    """One row per session: who, group, mode, participant, scenario, outcome, duration and seconds per step."""
    steps = sessions_svc.STEPS
    with connection() as conn:
        data = metrics.session_list(conn, {"mode": mode, "group": group}, 1, 100000)
    rows = [[i["id"], i["actor"], i["user_group"], i["mode"], i["participant_id"], i["scenario"], i["status"],
             i["duration_seconds"], i["root_cause"], i["repeat_detected"], i["failure_status"]]
            + [i["step_seconds"].get(s) for s in steps] for i in data["items"]]
    return _csv(["session_id", "user", "group", "mode", "participant", "scenario", "status", "duration_s", "root_cause",
                 "repeat", "failure"] + [f"{s}_s" for s in steps], rows, "sessions.csv")


@router.get("/api/export/labels-sample.csv", summary="Blind labelling sample as CSV")
def export_labels(limit: int = Query(50, ge=1, le=500), user: dict = Depends(require("evaluate"))):
    """Blank ``expert_cause`` column for the three process owners to fill in; AI and saved cause are hidden."""
    with connection() as conn:
        items = _sample(conn, user["id"], limit)
    return _csv(["complaint_id", "language", "description", "expert_cause"],
                [[i["id"], i["language"], i["description"], ""] for i in items], "labels-sample.csv")
