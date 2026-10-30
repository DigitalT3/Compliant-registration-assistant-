"""Root-cause analysis after the build (FR-18 to FR-20): themes in the "Other" reasons, a proposed shorter list, a re-label test."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import require
from ..dbutil import connection
from ..services import root_cause_analysis as rca

router = APIRouter(tags=["root-cause analysis"])


class ThemesIn(BaseModel):
    include_seed: bool = True
    min_theme_size: int = Field(2, ge=1, le=50)


class ProposalIn(BaseModel):
    max_categories: int = Field(8, ge=3, le=12)


class ReviewIn(BaseModel):
    decision: str = Field(..., pattern="^(agree|changes_requested)$")
    comment: str | None = Field(None, max_length=500)


@router.get("/api/rca", summary="Latest themes, proposed list and re-label result")
def overview(user: dict = Depends(require("rca_view"))):
    with connection() as conn:
        return rca.overview(conn)


@router.post("/api/rca/themes", summary="FR-18: cluster the 'Other' reasons into themes")
def themes(body: ThemesIn, user: dict = Depends(require("rca_run"))):
    with connection() as conn:
        return rca.run_themes(conn, user, body.include_seed, body.min_theme_size)


@router.post("/api/rca/proposal", summary="FR-19: propose a shorter list from the themes")
def proposal(body: ProposalIn, user: dict = Depends(require("rca_run"))):
    with connection() as conn:
        return rca.build_proposal(conn, user, body.max_categories)


@router.post("/api/rca/proposal/review", summary="FR-19: agree to the proposed list or ask for changes")
def proposal_review(body: ReviewIn, user: dict = Depends(require("review_taxonomy"))):
    with connection() as conn:
        return rca.review_proposal(conn, user, body.decision, body.comment)


@router.post("/api/rca/relabel", summary="FR-20: re-label the expert-labelled complaints with the current list")
def relabel(user: dict = Depends(require("rca_run"))):
    with connection() as conn:
        return rca.run_relabel(conn, user)
