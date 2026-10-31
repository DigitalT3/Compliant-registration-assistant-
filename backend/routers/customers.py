"""Customer lookup, context and prefill endpoints."""
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from .. import db
from ..auth import require
from ..dbutil import audit, connection
from ..services import lookup, masterdata, prefill, sessions

router = APIRouter(tags=["customers"])


class PrefillIn(BaseModel):
    """Prefill request: selected customer/site/order, type for defaults and current field state."""
    customer_id: str
    site_id: str | None = None
    order_id: str | None = None
    complaint_type: str | None = None
    origin: str | None = Field(default=None, pattern="^(search|email)$")   # how the complaint arrived: sets the channel default
    current_fields: dict[str, dict] = Field(default_factory=dict)
    session_id: str | None = None
    guess_site: bool = False       # a customer was just chosen: fill the site from the latest order when the search gave none


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
def get_context(customer_id: str, site_id: str | None = None, all: bool = False,
                user: dict = Depends(require("read"))):
    """Return the registration context for a customer (``all=true``: up to 200 orders instead of 10)."""
    with connection() as conn:
        return lookup.context(conn, customer_id, site_id, everything=all)


@router.post("/api/prefill", summary="Prefill and defaults with provenance")
def do_prefill(body: PrefillIn, user: dict = Depends(require("register"))):
    """Return fields with provenance (prefilled/default/manual/edited/blank) and log it when a session is given."""
    with connection() as conn:
        ctx = lookup.context(conn, body.customer_id)
        fields = prefill.build_prefill(ctx, user, body.site_id, body.order_id, body.guess_site)
        fields.update({k: v for k, v in body.current_fields.items() if v.get("provenance") in ("manual", "edited")})
        fields = prefill.apply_defaults(body.complaint_type, fields, body.origin)
        if body.session_id:
            sessions.get_open(conn, body.session_id, user)
            with db.pipeline(conn):                                          # one round trip for all the field rows
                for name, f in fields.items():
                    conn.execute("INSERT INTO field_events(session_id,field,origin,event_type,changed,at) VALUES(?,?,?,?,0,?)",
                                 (body.session_id, name, f["provenance"], "field", db.now()))
            conn.commit()
        return {"fields": fields}


class SiteIn(BaseModel):
    name: str = Field(max_length=80)
    postcode: str | None = Field(default=None, max_length=10)


class ContractIn(BaseModel):
    site_id: str = Field(max_length=40)
    valid_from: str | None = Field(default=None, max_length=10)
    valid_to: str | None = Field(default=None, max_length=10)


class ContainerIn(BaseModel):
    site_id: str = Field(max_length=40)
    number: str | None = Field(default=None, max_length=30)


class OrderIn(BaseModel):
    site_id: str = Field(max_length=40)
    container: str = Field(max_length=30)
    contract_id: str | None = Field(default=None, max_length=40)
    date: str | None = Field(default=None, max_length=10)


@router.post("/api/customers/{customer_id}/sites", status_code=201, summary="Add a site (customer_data permission)")
def add_site(customer_id: str, body: SiteIn, user: dict = Depends(require("customer_data"))):
    """PoC customer data only: marked as added in the PoC and audited."""
    with connection() as conn:
        return masterdata.add_site(conn, user, customer_id, body.name, body.postcode)


@router.post("/api/customers/{customer_id}/contracts", status_code=201, summary="Add a contract for a site")
def add_contract(customer_id: str, body: ContractIn, user: dict = Depends(require("customer_data"))):
    with connection() as conn:
        return masterdata.add_contract(conn, user, customer_id, body.site_id, body.valid_from, body.valid_to)


@router.post("/api/customers/{customer_id}/containers", status_code=201, summary="Add a container for a site")
def add_container(customer_id: str, body: ContainerIn, user: dict = Depends(require("customer_data"))):
    with connection() as conn:
        return masterdata.add_container(conn, user, customer_id, body.site_id, body.number)


@router.post("/api/customers/{customer_id}/orders", status_code=201, summary="Add an order for a site and container")
def add_order(customer_id: str, body: OrderIn, user: dict = Depends(require("customer_data"))):
    with connection() as conn:
        return masterdata.add_order(conn, user, customer_id, body.site_id, body.container, body.contract_id, body.date)


class CustomerIn(BaseModel):
    name: str = Field(max_length=120)
    postcode: str | None = Field(default=None, max_length=10)
    first_site: str | None = Field(default=None, max_length=80)


@router.get("/api/customers", summary="All customers with their data counts (customer_data permission)")
def list_customers(q: str | None = Query(default=None, max_length=100), limit: int = Query(default=50, ge=1, le=200),
                   offset: int = Query(default=0, ge=0), user: dict = Depends(require("customer_data"))):
    with connection() as conn:
        return masterdata.list_customers(conn, q, limit, offset)


@router.post("/api/customers", status_code=201, summary="Add a customer (customer_data permission)")
def add_customer(body: CustomerIn, user: dict = Depends(require("customer_data"))):
    """Takes the next customer number. An optional first site makes the customer usable straight away."""
    with connection() as conn:
        return masterdata.add_customer(conn, user, body.name, body.postcode, body.first_site)


@router.get("/api/customer-data/{section}", summary="Sites, contracts, orders or containers across all customers")
def customer_data(section: str = Path(pattern="^(sites|contracts|orders|containers)$"),
                  customer_id: str | None = Query(default=None, max_length=40), q: str | None = Query(default=None, max_length=100),
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                  user: dict = Depends(require("customer_data"))):
    with connection() as conn:
        return masterdata.list_rows(conn, section, customer_id, q, limit, offset)
