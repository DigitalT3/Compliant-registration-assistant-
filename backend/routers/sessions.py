"""Session and event recording plus analytics endpoints."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import cache
from ..auth import require
from ..dbutil import connection
from ..services import metrics, scope, sessions

router = APIRouter(tags=["sessions", "analytics"])


class SessionIn(BaseModel):
    """Start a session (optionally tagging a scripted scenario)."""
    scenario: str | None = Field(None, max_length=20)
    mode: str = Field("assistant", max_length=10, description="assistant or plain")
    participant_id: str | None = Field(None, max_length=40, description="Test participant tag (timed user test)")
    opened_seconds_ago: float = Field(0, ge=0, le=86400, description="How long the form had been open when the customer was chosen "
                                      "(client-measured elapsed time; the session starts that long ago, capped by the idle cap)")


class EventIn(BaseModel):
    """Client event; timestamps are stamped by the server."""
    type: str
    step: str | None = None
    field: str | None = Field(None, max_length=50)
    origin: str | None = None
    changed: bool = False


class CompleteIn(BaseModel):
    """Close a session as abandoned or failed (saved is recorded by the backend)."""
    outcome: str
    failure_status: str | None = Field(None, max_length=100)


@router.post("/api/sessions", status_code=201, summary="Start a registration session")
def start(body: SessionIn, user: dict = Depends(require("register"))):
    """Create a session; returns its ID."""
    with connection() as conn:
        return sessions.start(conn, user, body.scenario, body.mode, body.participant_id, body.opened_seconds_ago)


@router.post("/api/sessions/{session_id}/events", summary="Record a step or field event")
def event(session_id: str, body: EventIn, user: dict = Depends(require("register"))):
    """Record a step/field/validation event."""
    with connection() as conn:
        return sessions.add_event(conn, session_id, user, body.model_dump())


@router.post("/api/sessions/{session_id}/complete", summary="Close a session as abandoned or failed")
def complete(session_id: str, body: CompleteIn, user: dict = Depends(require("register"))):
    """Close the session; claiming 'saved' is rejected."""
    with connection() as conn:
        return sessions.close(conn, session_id, body.outcome, user, body.failure_status)


def _filters(date_from, date_to, complaint_type, root_cause, repeat, scenario, group, group_by=None,
             mode=None, participant=None):
    return {"date_from": date_from, "date_to": date_to, "complaint_type": complaint_type, "root_cause": root_cause,
            "repeat": repeat, "scenario": scenario, "group": group, "group_by": group_by, "mode": mode,
            "participant": participant}


@router.get("/api/analytics/summary", summary="Metrics from recorded data")
def summary(date_from: str | None = None, date_to: str | None = None, complaint_type: str | None = None,
            root_cause: str | None = None, repeat: bool | None = None, scenario: str | None = None,
            group: str | None = None, mode: str | None = Query(None, pattern="^(assistant|plain)$"),
            participant: str | None = None,
            group_by: str | None = Query(None, pattern="^(group|scenario|mode|participant)$"),
            user: dict = Depends(require("analytics"))):
    """Aggregate metrics with sample sizes; ``empty=true`` when nothing is recorded."""
    f = scope.scoped(user, _filters(date_from, date_to, complaint_type, root_cause, repeat, scenario, group,
                                    group_by, mode, participant))
    def compute():
        with connection() as conn:
            return metrics.summary(conn, f)
    out = cache.remember(("summary", user["id"], tuple(sorted((k, str(v)) for k, v in f.items()))), compute)
    team = scope.lead_team(user)
    return {**out, "scope": {"team": team}} if team else out


@router.get("/api/analytics/employees", summary="How each employee registers (team leads see their own team)")
def employees(group: str | None = None, mode: str | None = Query(None, pattern="^(assistant|plain)$"),
              user: dict = Depends(require("analytics"))):
    """Per-employee volume, time and its spread, and how much of the assistant's text and cause is kept.

    A team lead only gets the people of the team they lead. Shares based on fewer than ``report.per_employee_min_n``
    registrations are hidden (``value`` is null).
    """
    f = scope.scoped(user, _filters(None, None, None, None, None, None, group, mode=mode))
    def compute():
        with connection() as conn:
            return metrics.employee_breakdown(conn, f)
    out = cache.remember(("employees", user["id"], tuple(sorted((k, str(v)) for k, v in f.items()))), compute)
    team = scope.lead_team(user)
    return {**out, "scope": {"team": team}} if team else out


@router.get("/api/analytics/sessions", summary="Per-session records")
def session_rows(date_from: str | None = None, date_to: str | None = None, complaint_type: str | None = None,
                 root_cause: str | None = None, repeat: bool | None = None, scenario: str | None = None,
                 group: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 user: dict = Depends(require("analytics"))):
    """Paginated sessions with derived durations."""
    f = scope.scoped(user, _filters(date_from, date_to, complaint_type, root_cause, repeat, scenario, group))
    with connection() as conn:
        return metrics.session_list(conn, f, page, page_size)
