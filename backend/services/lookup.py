"""Customer lookup by customer number, order reference, container id, name or postcode (FR-01, FR-03)."""
import re

from ..errors import ApiError

_POSTCODE = re.compile(r"^\d{4}[A-Z]{0,2}$")  # NL "3133KJ" / BE "2030"; spaces and case are ignored


def _card(conn, cust, matched_site=None, matched_order=None) -> dict:
    sites = [dict(r) for r in conn.execute(
        "SELECT id,name,reference,postcode FROM sites WHERE customer_id=? ORDER BY id", (cust["id"],))]
    last = conn.execute("SELECT max(date) FROM orders WHERE customer_id=?", (cust["id"],)).fetchone()[0]
    site = next((x for x in sites if x["id"] == matched_site), None)
    order = matched_order and conn.execute("SELECT reference,container FROM orders WHERE id=?",
                                           (matched_order,)).fetchone()
    return {"customer_id": cust["id"], "number": cust["number"], "name": cust["name"],
            "postcode": cust["postcode"], "sites": sites, "last_order_date": last,
            "matched_site_id": matched_site, "matched_order_id": matched_order,
            "matched_site_name": site and site["name"],
            "matched_order_reference": order and order["reference"],
            "matched_container": order and order["container"]}


_DETAIL_MAX_CANDIDATES = 5   # two extra queries per card: skip them for broad searches that return many customers


def _detail(conn, card: dict) -> None:
    """Add the customer's contracts and its three most recent orders (at the matched site, if any) to a result card."""
    card["contracts"] = [
        {"id": r["id"], "reference": r["reference"], "site_id": r["site_id"], "valid_to": (r["valid_to"] or "")[:10],
         "active": r["status"] == "active"}
        for r in conn.execute("SELECT id,reference,site_id,status,valid_to FROM contracts WHERE customer_id=? "
                              "ORDER BY id", (card["customer_id"],))]
    sql, args = "SELECT id,reference,container,site_id,date,status FROM orders WHERE customer_id=?", [card["customer_id"]]
    if card["matched_site_id"]:
        sql, args = sql + " AND site_id=?", args + [card["matched_site_id"]]
    card["recent_orders"] = [dict(r) | {"date": (r["date"] or "")[:10]}
                             for r in conn.execute(sql + " ORDER BY date DESC LIMIT 3", args)]


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
    cands, mtype, orders = [], "none", []

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
    if not cands and mtype == "none":      # a container added in the PoC may not have any order yet
        box = conn.execute("SELECT * FROM containers WHERE lower(number)=lower(?)", (q,)).fetchone()
        if box:
            cust = conn.execute("SELECT * FROM customers WHERE id=?", (box["customer_id"],)).fetchone()
            card = _card(conn, cust, box["site_id"])
            card["matched_container"] = box["number"]
            cands, mtype = [card], "container"
    if mtype in ("order", "container") and orders:
        seen = {}
        for o in orders:
            seen.setdefault(o["customer_id"], o)
        for cid, o in seen.items():
            cust = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
            card = _card(conn, cust, o["site_id"], o["id"] if mtype == "order" else None)
            if mtype == "container":
                card["matched_container"] = o["container"]
            cands.append(card)
    if not cands:
        rows = conn.execute("SELECT * FROM customers WHERE lower(name) LIKE ? ESCAPE '\\' ORDER BY name",
                            (_like(q),)).fetchall()
        if rows:
            mtype, cands = "name", [_card(conn, r) for r in rows]
    if not cands:
        pc = re.sub(r"\s+", "", q).upper()
        if _POSTCODE.match(pc):
            rows = conn.execute(
                "SELECT DISTINCT c.* FROM customers c LEFT JOIN sites s ON s.customer_id=c.id "
                "WHERE replace(upper(c.postcode),' ','') LIKE ? OR replace(upper(s.postcode),' ','') LIKE ? "
                "ORDER BY c.name", (pc + "%", pc + "%")).fetchall()
            if rows:
                mtype, cands = "postcode", []
                for r in rows:
                    site = conn.execute("SELECT id FROM sites WHERE customer_id=? AND "
                                        "replace(upper(postcode),' ','') LIKE ? ORDER BY id LIMIT 1",
                                        (r["id"], pc + "%")).fetchone()
                    cands.append(_card(conn, r, site and site["id"]))
    cands.sort(key=lambda c: c["last_order_date"] or "", reverse=True)
    if len(cands) <= _DETAIL_MAX_CANDIDATES:
        for card in cands:
            _detail(conn, card)
    return {"query": q, "match_type": mtype if cands else "none", "ambiguous": len(cands) > 1,
            "count": len(cands), "candidates": cands}


_LEGAL = re.compile(r"[\s,]+(b\.?v\.?|n\.?v\.?|v\.?o\.?f\.?|vof|bv|nv)\s*$", re.I)
_NAME_MIN = 6            # shorter names are too likely to occur by chance in a text


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


# PUBLIC_INTERFACE
def find_in_text(conn, text: str) -> tuple[str | None, str | None]:
    """Find the customer an e-mail is about when it has no usable number: by company name, then by postcode.

    Returns ``(customer number, matched_by)`` or ``(None, None)``. A name counts when it occurs as whole words
    (the legal form BV/NV/VOF may be left out); the longest name wins. Two different customers matching equally
    is not decided here: the answer is None and the employee searches by hand.
    """
    plain, hits = " " + _plain(text) + " ", []
    for r in conn.execute("SELECT number, name FROM customers WHERE active=1").fetchall():
        for name in {_plain(r["name"]), _plain(_LEGAL.sub("", r["name"]))}:
            if len(name) >= _NAME_MIN and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", plain):
                hits.append((len(name), r["number"]))
    if hits:
        best = max(h[0] for h in hits)
        numbers = {n for ln, n in hits if ln == best}
        return (numbers.pop(), "name") if len(numbers) == 1 else (None, None)
    for pc in dict.fromkeys(re.findall(r"\b(\d{4})\s?([A-Za-z]{2})\b", text)):
        found = search(conn, "".join(pc))
        if found["match_type"] == "postcode" and found["count"] == 1:
            return found["candidates"][0]["number"], "postcode"
    return None, None


# PUBLIC_INTERFACE
def context(conn, customer_id: str, site_id: str | None = None, everything: bool = False) -> dict:
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
    orders = [dict(r) for r in conn.execute(sql + f" ORDER BY date DESC LIMIT {200 if everything else 10}", args)]
    containers = [dict(r) for r in conn.execute("SELECT * FROM containers WHERE customer_id=? ORDER BY number", (customer_id,))]
    return {"customer": dict(cust), "sites": sites, "contracts": contracts, "orders": orders, "containers": containers}
