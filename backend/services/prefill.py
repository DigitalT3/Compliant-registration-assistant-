"""Prefill and config-driven defaults with per-field provenance (FR-04..FR-06).

Provenance values: prefilled, default, manual, edited, blank.
"""
from .. import db
from ..settings import get_config

PROVENANCE = {"prefilled", "default", "manual", "edited", "blank"}


def _f(value, prov=None):
    if value in (None, ""):
        return {"value": None, "provenance": "blank"}
    return {"value": value, "provenance": prov}


# PUBLIC_INTERFACE
def build_prefill(ctx: dict, user: dict, site_id=None, order_id=None) -> dict:
    """Build prefilled fields from customer context. A site is only filled when
    unambiguous (explicitly chosen or the customer has exactly one)."""
    cust, sites = ctx["customer"], ctx["sites"]
    if not site_id and len(sites) == 1:
        site_id = sites[0]["id"]
    contract = next((c for c in ctx["contracts"] if c["site_id"] == site_id and c["active"]), None)
    return {
        "customer_id": _f(cust["id"], "prefilled"),
        "customer_number": _f(cust["number"], "prefilled"),
        "customer_name": _f(cust["name"], "prefilled"),
        "site_id": _f(site_id, "prefilled"),
        "contract_id": _f(contract["id"] if contract else None, "prefilled"),
        "order_id": _f(order_id, "prefilled"),
        "registering_user": _f(user["id"], "prefilled"),
        "registration_date": _f(db.reference_now().date().isoformat(), "prefilled"),
    }


# PUBLIC_INTERFACE
def apply_defaults(complaint_type: str | None, current: dict | None) -> dict:
    """Apply configured defaults for ``complaint_type`` to fields that are blank.

    Fields with provenance manual/edited, or already holding a value, are never overwritten.
    """
    fields = {k: dict(v) for k, v in (current or {}).items()}
    for name, value in get_config()["defaults"].get(complaint_type or "", {}).items():
        cur = fields.get(name)
        if cur and (cur.get("provenance") in ("manual", "edited") or cur.get("value") not in (None, "")):
            continue
        fields[name] = {"value": value, "provenance": "default"}
    return fields
