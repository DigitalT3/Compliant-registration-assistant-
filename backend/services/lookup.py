"""Customer lookup by customer number, order reference, container id or name (FR-01, FR-03)."""
from ..errors import ApiError


def _card(conn, cust, matched_site=None, matched_order=None) -> dict:
    sites = [dict(r) for r in conn.execute(
        "SELECT id,name,reference,postcode FROM sites WHERE customer_id=? ORDER BY id", (cust["id"],))]
    last = conn.execute("SELECT max(date) FROM orders WHERE customer_id=?", (cust["id"],)).fetchone()[0]
    return {"customer_id": cust["id"], "number": cust["number"], "name": cust["name"],
            "postcode": cust["postcode"], "sites": sites, "last_order_date": last,
            "matched_site_id": matched_site, "matched_order_id": matched_order}


def _like(q: str) -> str:
    return "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# PUBLIC_INTERFACE
def search(conn, q: str) -> dict:
    """Classify ``q`` and return ``{match_type, ambiguous, count, candidates[]}``.

    Never auto-selects: several candidates are returned as ``ambiguous``; no
    candidates gives ``match_type='none'``. Most recent order first.
    """
    q = (q or "").strip()
    if not q:
        raise ApiError(400, "empty_query", "Enter a customer number, order, container or name.")
    cands, mtype = [], "none"

    rows = conn.execute("SELECT * FROM customers WHERE number=?", (q,)).fetchall()
    if rows:
        mtype, cands = "customer_number", [_card(conn, r) for r in rows]
    if not cands:
        orders = conn.execute("SELECT * FROM orders WHERE lower(reference)=lower(?) ORDER BY date DESC",
                              (q,)).fetchall()
        if orders:
            mtype = "order"
    if not cands and mtype == "none":
        orders = conn.execute("SELECT * FROM orders WHERE lower(container)=lower(?) ORDER BY date DESC",
                              (q,)).fetchall()
        if orders:
            mtype = "container"
    if mtype in ("order", "container"):
        seen = {}
        for o in orders:
            seen.setdefault(o["customer_id"], o)
        for cid, o in seen.items():
            cust = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
            cands.append(_card(conn, cust, o["site_id"], o["id"] if mtype == "order" else None))
    if not cands:
        rows = conn.execute("SELECT * FROM customers WHERE lower(name) LIKE ? ESCAPE '\\' ORDER BY name",
                            (_like(q),)).fetchall()
        if rows:
            mtype, cands = "name", [_card(conn, r) for r in rows]
    cands.sort(key=lambda c: c["last_order_date"] or "", reverse=True)
    return {"query": q, "match_type": mtype if cands else "none", "ambiguous": len(cands) > 1,
            "count": len(cands), "candidates": cands}


# PUBLIC_INTERFACE
def context(conn, customer_id: str, site_id: str | None = None) -> dict:
    """Return customer, sites, contracts and the last 10 orders (optionally per site)."""
    cust = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not cust:
        raise ApiError(404, "customer_not_found", "Customer not found.")
    sites = [dict(r) for r in conn.execute("SELECT * FROM sites WHERE customer_id=? ORDER BY id", (customer_id,))]
    contracts = []
    for r in conn.execute("SELECT * FROM contracts WHERE customer_id=? ORDER BY id", (customer_id,)):
        d = dict(r)
        d["active"] = d["status"] == "active"
        contracts.append(d)
    sql, args = "SELECT * FROM orders WHERE customer_id=?", [customer_id]
    if site_id:
        sql, args = sql + " AND site_id=?", args + [site_id]
    orders = [dict(r) for r in conn.execute(sql + " ORDER BY date DESC LIMIT 10", args)]
    return {"customer": dict(cust), "sites": sites, "contracts": contracts, "orders": orders}
