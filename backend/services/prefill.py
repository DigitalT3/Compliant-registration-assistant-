"""Prefill and config-driven defaults with per-field provenance (FR-04..FR-06).

Provenance values: prefilled, default, manual, edited, blank.
"""
from datetime import datetime, timezone

from ..settings import get_config

try:
    from zoneinfo import ZoneInfo
    _LOCAL = ZoneInfo("Europe/Amsterdam")
except Exception:                                  # no time-zone data on this machine: use UTC
    _LOCAL = timezone.utc

PROVENANCE = {"prefilled", "default", "suggested", "manual", "edited", "blank"}


def _f(value, prov=None):
    if value in (None, ""):
        return {"value": None, "provenance": "blank"}
    return {"value": value, "provenance": prov}


# PUBLIC_INTERFACE
def today() -> str:
    """Today's date where the employees work (the real date, not the fixed clock the seeded history uses)."""
    return datetime.now(_LOCAL).date().isoformat()


def _guess_site(ctx: dict):
    """The site to prefill when the search did not point at one: the customer's only site, else the site of the
    latest order, else the only site with an active contract. Otherwise None (the employee chooses)."""
    sites = ctx["sites"]
    if len(sites) == 1:
        return sites[0]["id"]
    if ctx["orders"]:
        return ctx["orders"][0]["site_id"]            # orders arrive newest first
    with_contract = {c["site_id"] for c in ctx["contracts"] if c["active"]}
    return next(iter(with_contract)) if len(with_contract) == 1 else None


# PUBLIC_INTERFACE
def build_prefill(ctx: dict, user: dict, site_id=None, order_id=None, guess_site: bool = False) -> dict:
    """Build prefilled fields from customer context. With ``guess_site`` (a customer was just chosen) the site is
    filled even when the search did not point at one (see ``_guess_site``); otherwise it is only filled when
    explicitly given or the customer has exactly one. When no order was matched, the most recent order at the
    site is prefilled (with its container)."""
    cust, sites = ctx["customer"], ctx["sites"]
    if not site_id and (guess_site or len(sites) == 1):
        site_id = _guess_site(ctx)
    contract = next((c for c in ctx["contracts"] if c["site_id"] == site_id and c["active"]), None)
    if not order_id and site_id:
        order_id = next((o["id"] for o in ctx["orders"] if o["site_id"] == site_id), None)
    order = next((o for o in ctx["orders"] if o["id"] == order_id), None)
    return {
        "customer_id": _f(cust["id"], "prefilled"),
        "customer_number": _f(cust["number"], "prefilled"),
        "customer_name": _f(cust["name"], "prefilled"),
        "site_id": _f(site_id, "prefilled"),
        "contract_id": _f(contract["id"] if contract else None, "prefilled"),
        "order_id": _f(order_id, "prefilled"),
        "container": _f(order["container"] if order else None, "prefilled"),
        "registering_user": _f(user["id"], "prefilled"),
        "registration_date": _f(today(), "prefilled"),
    }


# PUBLIC_INTERFACE
def apply_defaults(complaint_type: str | None, current: dict | None, origin: str | None = None) -> dict:
    """Apply configured defaults (``_all`` plus the type's) to fields that are blank.

    ``origin`` says how the complaint arrived ("search": the customer is on the phone, "email": started from a
    pasted email); it sets the channel, because that is a fact about this complaint, not about its type.
    Fields with provenance manual/edited, or already holding a value, are never overwritten.
    """
    fields = {k: dict(v) for k, v in (current or {}).items()}
    cfg = get_config()
    defaults = cfg["defaults"]
    merged = {**defaults.get("_all", {}), **defaults.get(complaint_type or "", {})}
    by_origin = cfg.get("origin_defaults", {}).get(origin or "")
    if by_origin:
        merged["channel"] = by_origin
    for name, value in merged.items():
        cur = fields.get(name)
        if cur and (cur.get("provenance") in ("manual", "edited") or cur.get("value") not in (None, "")):
            continue
        fields[name] = {"value": value, "provenance": "default"}
    return fields
