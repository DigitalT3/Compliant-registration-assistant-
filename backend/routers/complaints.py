"""AI-assisted steps, repeat check and complaint persistence endpoints."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..auth import require
from ..dbutil import connection
from ..services import ai, complaints, lookup
from ..settings import get_config

router = APIRouter(tags=["complaints"])
Lang = Optional[Literal["nl", "en"]]


class ExtractIn(BaseModel):
    """Pasted email text."""
    text: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None


class SummariseIn(BaseModel):
    """Complaint text plus minimal selected context."""
    text: str = Field(..., min_length=1, max_length=8000)
    language: Lang = None
    site_id: str | None = None
    customer_id: str | None = None
    session_id: str | None = None


class ClassifyIn(BaseModel):
    """Complaint text, optional summary and session for logging."""
    text: str = Field(..., min_length=1, max_length=8000)
    summary: dict | None = None
    language: Lang = None
    session_id: str | None = None


class RepeatIn(BaseModel):
    """Repeat-check inputs."""
    customer_id: str | None = None
    site_id: str | None = None
    root_cause: str | None = None
    session_id: str | None = None


class ComplaintIn(BaseModel):
    """Complaint to save (PoC database only)."""
    customer_id: str
    site_id: str | None = None
    contract_id: str | None = None
    order_id: str | None = None
    channel: str = Field("", max_length=30)
    complaint_type: str = ""
    root_cause: str = ""
    other_reason: str | None = Field(None, max_length=500)
    description: str = Field("", max_length=8000)
    language: Lang = None
    summary: dict | None = None
    summary_meta: dict | None = None
    session_id: str | None = None
    scenario: str | None = None
    repeat_input_hash: str | None = None


@router.post("/api/complaints/extract", summary="Extract candidates from pasted email (Should)")
def extract(body: ExtractIn, user: dict = Depends(require("register"))):
    """Return extraction candidates, each flagged as validated against the customer DB or uncertain."""
    with connection() as conn:
        out = ai.run(conn, "extract", {"text": body.text}, body.session_id, user["id"])
        if out["ai_status"] == "ok":
            r = out["result"]
            r["validation"] = {
                "customer_number": None if not r["customer_number"] else bool(lookup.search(conn, r["customer_number"])["count"]),
                "order_reference": None if not r["order_reference"] else bool(lookup.search(conn, r["order_reference"])["count"]),
                "container": None if not r["container"] else bool(lookup.search(conn, r["container"])["count"])}
        return out


@router.post("/api/complaints/summarise", summary="Structured summary")
def summarise(body: SummariseIn, user: dict = Depends(require("register"))):
    """Return a validated summary or ``ai_status=failed`` (manual entry stays possible)."""
    with connection() as conn:
        site_name = None
        if body.site_id:
            r = conn.execute("SELECT name FROM sites WHERE id=?", (body.site_id,)).fetchone()
            site_name = r and r["name"]
        return ai.run(conn, "summarise", {"text": body.text, "language": body.language, "site_name": site_name},
                      body.session_id, user["id"])


@router.post("/api/complaints/classify", summary="Type and top-three root-cause candidates")
def classify(body: ClassifyIn, user: dict = Depends(require("register"))):
    """Return candidates; below ``classification.min_confidence`` nothing is preselected."""
    cfg = get_config()
    payload = {"text": body.text, "summary": body.summary, "language": body.language,
               "taxonomy": cfg["root_causes"], "types": [t["id"] for t in cfg["types"]]}
    with connection() as conn:
        out = ai.run(conn, "classify", payload, body.session_id, user["id"])
    out["taxonomy_version"] = cfg["taxonomy_version"]
    if out["ai_status"] == "ok":
        cands = out["result"]["candidates"]
        top = cands[0]["confidence"] if cands else 0
        low = top < cfg["classification"]["min_confidence"]
        out.update({"low_confidence": low, "preselect": None if low else cands[0]["root_cause_id"],
                    "min_confidence": cfg["classification"]["min_confidence"],
                    "confidence_note": "Heuristic score, not a calibrated probability."})
    return out


@router.post("/api/complaints/check-repeat", summary="Deterministic repeat check")
def check_repeat(body: RepeatIn, user: dict = Depends(require("register"))):
    """Return repeat result, matching IDs, count, evidence, rule version and check timestamp."""
    with connection() as conn:
        res = complaints.check_repeat(conn, body.model_dump(exclude={"session_id"}), body.session_id)
        conn.commit()
        return {**res, "matching_ids": [m["id"] for m in res["matches"]]}


@router.post("/api/complaints", status_code=201, summary="Save complaint to the PoC database")
def create(body: ComplaintIn, user: dict = Depends(require("register"))):
    """Atomically save complaint, repeat evidence, events and audit. Returns ``POC-<seq>``."""
    with connection() as conn:
        return complaints.create(conn, body.model_dump(), user)


@router.get("/api/complaints", summary="Complaint history (paginated)")
def list_(customer_id: str | None = None, customer_number: str | None = None, complaint_type: str | None = None,
          root_cause: str | None = None, status: str | None = None, date_from: str | None = None,
          date_to: str | None = None, repeat: bool | None = None, include_seed: bool = True,
          page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
          user: dict = Depends(require("read"))):
    """List complaints with optional filters."""
    f = {"customer_id": customer_id, "customer_number": customer_number, "complaint_type": complaint_type,
         "root_cause": root_cause, "status": status, "date_from": date_from, "date_to": date_to,
         "repeat": repeat, "include_seed": include_seed}
    with connection() as conn:
        return complaints.list_complaints(conn, f, page, page_size)


@router.get("/api/complaints/{complaint_id}", summary="Complaint detail")
def get_one(complaint_id: str, user: dict = Depends(require("read"))):
    """Return a complaint with repeat evidence and disputes."""
    with connection() as conn:
        return complaints.get(conn, complaint_id)
