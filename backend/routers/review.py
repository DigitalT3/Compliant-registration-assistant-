"""Repeat disputes (FR-13, Could), evaluations and synthetic Other-reason grouping (later phase)."""
import json
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db
from ..auth import require
from ..dbutil import audit, connection
from ..errors import ApiError
from ..services import disputes, scope

router = APIRouter(tags=["review"])


class DisputeIn(BaseModel):
    """Employee decision on a repeat warning; the rule outcome is stored separately."""
    complaint_id: str
    prior_complaint_id: str
    decision: str = Field(..., pattern="^(confirm|reject)$")
    reason: str | None = Field(None, max_length=500)


class EvaluationIn(BaseModel):
    """Summary-quality rating and optional expert root-cause label."""
    complaint_id: str
    usable: bool
    expert_cause: str | None = None
    notes: str | None = Field(None, max_length=500)


@router.post("/api/repeat-disputes", status_code=201, summary="Record a repeat dispute")
def create_dispute(body: DisputeIn, user: dict = Depends(require("register"))):
    """Store the decision with the original rule evidence untouched in ``repeat_checks``.

    Only the person who registered the complaint (or an administrator) can decide, and only about an earlier complaint
    the rule actually linked to it. A dispute needs a reason of at least 3 characters.
    """
    with connection() as conn:
        owner = conn.execute("SELECT registering_user FROM complaints WHERE id=?", (body.complaint_id,)).fetchone()
        if not owner:
            raise ApiError(404, "complaint_not_found", "Complaint not found.")
        if owner["registering_user"] != user["id"] and user["role"] != "admin":
            raise ApiError(403, "not_your_complaint", "Only the person who registered the complaint can confirm or dispute its repeat links.")
        chk = conn.execute("SELECT matching_ids FROM repeat_checks WHERE complaint_id=? ORDER BY id DESC LIMIT 1", (body.complaint_id,)).fetchone()
        if not chk:
            raise ApiError(404, "repeat_check_not_found", "No stored repeat check for this complaint.")
        if body.prior_complaint_id not in json.loads(chk["matching_ids"] or "[]"):
            raise ApiError(422, "not_a_linked_complaint", "That complaint is not one of the earlier complaints the rule linked.")
        disputes.insert(conn, user["id"], body.complaint_id, body.prior_complaint_id, body.decision, disputes.clean(body.decision, body.reason))
        conn.commit()
        return {"recorded": True, "rule_outcome_unchanged": True}


@router.get("/api/repeat-disputes", summary="List repeat disputes")
def list_disputes(user: dict = Depends(require("read"))):
    """List decisions with who, when, both complaints and the original rule evidence."""
    with connection() as conn:
        return {"items": [dict(r, evidence=json.loads(r["evidence"] or "{}")) for r in disputes.listing(conn)], "review": disputes.review_status(conn)}


class DisputeReviewIn(BaseModel):
    note: str | None = Field(None, max_length=500)


@router.post("/api/repeat-disputes/review", summary="Record the weekly review of repeat decisions")
def review_disputes(body: DisputeReviewIn, user: dict = Depends(require("review_disputes"))):
    """Marks every decision not yet reviewed as reviewed by the caller (rule owner or administrator), with an optional note."""
    with connection() as conn:
        return disputes.mark_reviewed(conn, user, body.note)


@router.post("/api/evaluations", status_code=201, summary="Rate a summary / label the expert cause")
def create_eval(body: EvaluationIn, user: dict = Depends(require("evaluate"))):
    """Record an evaluation row."""
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM complaints WHERE id=?", (body.complaint_id,)).fetchone():
            raise ApiError(404, "complaint_not_found", "Complaint not found.")
        conn.execute("INSERT INTO evaluations(complaint_id,actor,usable,expert_cause,notes,at) VALUES(?,?,?,?,?,?)",
                     (body.complaint_id, user["id"], int(body.usable), body.expert_cause, body.notes, db.now()))
        conn.commit()
        return {"recorded": True}


@router.get("/api/evaluations", summary="Evaluations with agreement rate")
def list_evals(user: dict = Depends(require("evaluate"))):
    """Return evaluations, usable share and expert/final-cause agreement (with n)."""
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT e.*,c.root_cause final_cause FROM evaluations e JOIN complaints c ON c.id=e.complaint_id "
            "WHERE e.id IN (SELECT max(id) FROM evaluations GROUP BY complaint_id, actor) ORDER BY e.id DESC")]   # one rating per person per complaint: the latest
    lab = [r for r in rows if r["expert_cause"]]
    return {"items": rows, "usable": {"value": round(sum(r["usable"] for r in rows) / len(rows), 3) if rows else None, "n": len(rows)},
            "expert_agreement": {"value": round(sum(r["expert_cause"] == r["final_cause"] for r in lab) / len(lab), 3) if lab else None, "n": len(lab)}}


@router.get("/api/analysis/other-reasons", summary="Group 'Other' reasons (synthetic, later-phase readiness)")
def other_reasons(user: dict = Depends(require("analytics"))):
    """Group stored 'Other' reasons by normalised text. Exact-text grouping on synthetic data only;
    not a taxonomy-improvement analysis (FR-18..FR-20 remain later-phase)."""
    team = scope.lead_team(user)
    sql = "SELECT c.other_reason FROM complaints c WHERE c.root_cause='other' AND c.other_reason IS NOT NULL"
    args: tuple = ()
    if team:   # a team lead sees only their team's complaints
        sql += " AND c.session_id IN (SELECT id FROM sessions WHERE user_group=?)"
        args = (team,)
    with connection() as conn:
        c = Counter((r[0] or "").strip().lower() for r in conn.execute(sql, args))
    return {"synthetic": True, "later_phase": True, "n": sum(c.values()),
            "groups": [{"reason": k, "count": v} for k, v in c.most_common()]}
