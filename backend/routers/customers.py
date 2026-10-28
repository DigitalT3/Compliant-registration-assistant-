"""Customer lookup, context and prefill endpoints."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import db
from ..auth import require
from ..dbutil import audit, connection
from ..services import lookup, prefill, sessions

router = APIRouter(tags=["customers"])


class PrefillIn(BaseModel):
    """Prefill request: selected customer/site/order, type for defaults and current field state."""
    customer_id: str
    site_id: str | None = None
    order_id: str | None = None
    complaint_type: str | None = None
    current_fields: dict[str, dict] = Field(default_factory=dict)
    session_id: str | None = None


@router.get("/api/customers/search", summary="Search customers by number, order, container or name")
def search(q: str = Query(..., max_length=100), user: dict = Depends(require("read"))):
    """Return ``{match_type, ambiguous, count, candidates}``; ambiguous and no-match are explicit."""
    with connection() as conn:
        return lookup.search(conn, q)


@router.get("/api/customers/{customer_id}", summary="Customer details")
def get_customer(customer_id: str, user: dict = Depends(require("read"))):
    """Return customer and sites."""
    with connection() as conn:
        c = lookup.context(conn, customer_id)
        return {"customer": c["customer"], "sites": c["sites"]}


@router.get("/api/customers/{customer_id}/context", summary="Sites, contracts and last 10 orders")
def get_context(customer_id: str, site_id: str | None = None, user: dict = Depends(require("read"))):
    """Return the registration context for a customer."""
    with connection() as conn:
        return lookup.context(conn, customer_id, site_id)


@router.post("/api/prefill", summary="Prefill and defaults with provenance")
def do_prefill(body: PrefillIn, user: dict = Depends(require("register"))):
    """Return fields with provenance (prefilled/default/manual/edited/blank) and log it when a session is given."""
    with connection() as conn:
        ctx = lookup.context(conn, body.customer_id)
        fields = prefill.build_prefill(ctx, user, body.site_id, body.order_id)
        fields.update({k: v for k, v in body.current_fields.items() if v.get("provenance") in ("manual", "edited")})
        fields = prefill.apply_defaults(body.complaint_type, fields)
        if body.session_id:
            sessions.get_open(conn, body.session_id, user)
            for name, f in fields.items():
                conn.execute("INSERT INTO field_events(session_id,field,origin,event_type,changed,at) VALUES(?,?,?,?,0,?)",
                             (body.session_id, name, f["provenance"], "field", db.now()))
            conn.commit()
        return {"fields": fields}
