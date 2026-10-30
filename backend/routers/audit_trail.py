"""Audit trail: all saved records and how they were made, for administrators (audit permission)."""
from fastapi import APIRouter, Depends, Query

from ..auth import require
from ..dbutil import audit, connection
from ..services import audit_trail
from .testing import _csv

router = APIRouter(tags=["audit"])


@router.get("/api/audit/records", summary="Every saved record (administrators)")
def list_records(q: str | None = Query(None, max_length=100), include_seed: bool = True, page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100), user: dict = Depends(require("audit"))):
    """The PoC's own registrations newest first, then the synthetic history; ``q`` matches the id, customer name or number."""
    with connection() as conn:
        return audit_trail.records(conn, q, include_seed, page, page_size)


@router.get("/api/audit/records/{complaint_id}", summary="One record: target structure, field origins, repeat evidence, audit events")
def get_record(complaint_id: str, user: dict = Depends(require("audit"))):
    """The saved record in the target field structure and everything recorded about how it was made."""
    with connection() as conn:
        return audit_trail.detail(conn, complaint_id)


@router.get("/api/export/records.csv", summary="All saved records in the target field structure, as CSV")
def export_records(include_seed: bool = False, user: dict = Depends(require("audit"))):
    """One row per saved record, columns named as the target fields (placeholders). The export is written to the audit log."""
    with connection() as conn:
        header, rows = audit_trail.export_rows(conn, include_seed)
        audit(conn, user["id"], "records_exported", {"rows": len(rows), "include_seed": include_seed})
        conn.commit()
    return _csv(header, rows, "records.csv")
