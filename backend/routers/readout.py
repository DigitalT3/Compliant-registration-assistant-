"""Go/no-go readout for the business owner: evidence, open conditions and the recorded decision."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import require
from ..dbutil import connection
from ..services import readout
from .testing import _csv

router = APIRouter()


class DecisionIn(BaseModel):
    """The business owner's decision and the reason for it."""
    decision: str = Field(..., pattern="^(go|conditional|no_go)$")
    comment: str = Field(..., min_length=1, max_length=1000)


@router.get("/api/readout", tags=["readout"], summary="Evidence, open conditions and decisions for go/no-go")
def get_readout(user: dict = Depends(require("readout"))):
    """Targets with sample sizes, the baseline comparison, the open conditions and earlier decisions."""
    with connection() as conn:
        return readout.evidence(conn)


@router.post("/api/readout/decision", tags=["readout"], summary="Record the go/no-go decision")
def post_decision(body: DecisionIn, user: dict = Depends(require("decide"))):
    """Needs the ``decide`` permission (business owner). The decision is stored with the evidence it rests on."""
    with connection() as conn:
        return readout.decide(conn, user, body.decision, body.comment)


@router.get("/api/export/readout.csv", tags=["readout"], summary="The readout as CSV")
def export_readout(user: dict = Depends(require("readout"))):
    """Targets, conditions and decisions as a CSV file."""
    with connection() as conn:
        ev = readout.evidence(conn)
    return _csv(["section", "item", "value", "n_or_ok", "status_or_detail"], readout.csv_rows(ev), "readout.csv")
