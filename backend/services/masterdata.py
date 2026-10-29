"""Add sites, contracts, containers and orders for an existing customer (PoC customer data).

In Renewi's real landscape this data lives in the client's own systems and the PoC never writes to
them. Here it stands in for those systems so test scenarios can be extended. Every row added through
this module is marked ``source='poc_added'`` with who added it and when, and is audited.
"""
import re
from datetime import date, timedelta

from .. import db
from ..dbutil import audit
from ..errors import ApiError

_POSTCODE = re.compile(r"^\d{4}\s?[A-Za-z]{2}$")
_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{2,29}$")


def _customer(conn, customer_id: str):
    row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        raise ApiError(404, "customer_not_found", "Customer not found.")
    return row


def _site(conn, customer_id: str, site_id: str | None):
    row = site_id and conn.execute("SELECT * FROM sites WHERE id=? AND customer_id=?", (site_id, customer_id)).fetchone()
    if not row:
        raise ApiError(422, "invalid_site", "Choose one of this customer's sites.")
    return row


def _suffix(cust) -> str:
    return cust["number"][-3:]


def _next(conn, table: str, customer_id: str, marker: str) -> int:
    """Next number for ids like C009-S3 / C009-K3: one more than the highest existing."""
    ids = [r["id"] for r in conn.execute(f"SELECT id FROM {table} WHERE customer_id=?", (customer_id,))]
    nums = [int(m.group(1)) for i in ids if (m := re.search(rf"-{marker}(\d+)$", i))]
    return max(nums, default=0) + 1


def _stamp(conn, actor: dict, kind: str, row_id: str, extra=None) -> None:
    audit(conn, actor["id"], "customer_data_added", {"kind": kind, "id": row_id, **(extra or {})})


def _clean(text, label: str, lo: int, hi: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not lo <= len(text) <= hi:
        raise ApiError(422, "invalid_" + label, f"Enter {label} ({lo} to {hi} characters).")
    return text


def _iso(value, label: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(422, "invalid_date", f"{label} must be a date (YYYY-MM-DD).")


def add_site(conn, actor: dict, customer_id: str, name: str, postcode: str | None) -> dict:
    cust = _customer(conn, customer_id)
    name = _clean(name, "name", 2, 80)
    postcode = (postcode or "").strip()
    if postcode and not _POSTCODE.match(postcode):
        raise ApiError(422, "invalid_postcode", "Postcode must look like 1234 AB.")
    n = _next(conn, "sites", customer_id, "S")
    sid = f"{customer_id}-S{n}"
    conn.execute("INSERT INTO sites(id,customer_id,name,reference,postcode,active,source,created_by,created_at) "
                 "VALUES(?,?,?,?,?,1,'poc_added',?,?)",
                 (sid, customer_id, name, f"SITE-{_suffix(cust)}-{n}", postcode.replace(" ", "").upper() or cust["postcode"],
                  actor["id"], db.now()))
    _stamp(conn, actor, "site", sid)
    conn.commit()
    return dict(conn.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone())


def add_contract(conn, actor: dict, customer_id: str, site_id: str, valid_from, valid_to) -> dict:
    cust = _customer(conn, customer_id)
    _site(conn, customer_id, site_id)
    today = db.reference_now().date()
    start = _iso(valid_from or today.isoformat(), "Valid from")
    end = _iso(valid_to or (today + timedelta(days=365)).isoformat(), "Valid to")
    if end < start:
        raise ApiError(422, "invalid_dates", "Valid to cannot be before valid from.")
    n = _next(conn, "contracts", customer_id, "K")
    cid = f"{customer_id}-K{n}"
    conn.execute("INSERT INTO contracts(id,customer_id,site_id,status,reference,valid_from,valid_to,source,created_by,created_at) "
                 "VALUES(?,?,?,?,?,?,?,'poc_added',?,?)",
                 (cid, customer_id, site_id, "active" if end >= today else "expired", f"CON-{_suffix(cust)}-{n}",
                  start.isoformat(), end.isoformat(), actor["id"], db.now()))
    _stamp(conn, actor, "contract", cid, {"site": site_id})
    conn.commit()
    row = dict(conn.execute("SELECT * FROM contracts WHERE id=?", (cid,)).fetchone())
    row["active"] = row["status"] == "active"
    return row


def add_container(conn, actor: dict, customer_id: str, site_id: str, number: str | None) -> dict:
    cust = _customer(conn, customer_id)
    _site(conn, customer_id, site_id)
    number = (number or "").strip().upper()
    if not number:
        n = conn.execute("SELECT count(*) FROM containers WHERE customer_id=?", (customer_id,)).fetchone()[0] + 1
        number = f"BOX-{_suffix(cust)}-{n}"
        while conn.execute("SELECT 1 FROM containers WHERE lower(number)=lower(?)", (number,)).fetchone():
            n += 1
            number = f"BOX-{_suffix(cust)}-{n}"
    elif not _CONTAINER.match(number):
        raise ApiError(422, "invalid_container", "Container numbers use letters, digits and dashes (3 to 30 characters).")
    if conn.execute("SELECT 1 FROM containers WHERE lower(number)=lower(?)", (number,)).fetchone():
        raise ApiError(409, "container_exists", "A container with this number already exists.")
    conn.execute("INSERT INTO containers(id,customer_id,site_id,number,status,source,created_by,created_at) "
                 "VALUES(?,?,?,?, 'active','poc_added',?,?)",
                 (number, customer_id, site_id, number, actor["id"], db.now()))
    _stamp(conn, actor, "container", number, {"site": site_id})
    conn.commit()
    return dict(conn.execute("SELECT * FROM containers WHERE id=?", (number,)).fetchone())


def add_order(conn, actor: dict, customer_id: str, site_id: str, container: str, contract_id: str | None,
              order_date) -> dict:
    cust = _customer(conn, customer_id)
    _site(conn, customer_id, site_id)
    box = conn.execute("SELECT * FROM containers WHERE lower(number)=lower(?) AND site_id=?",
                       ((container or "").strip(), site_id)).fetchone()
    if not box:
        raise ApiError(422, "invalid_container", "Choose a container that belongs to this site (add it first).")
    if contract_id and not conn.execute("SELECT 1 FROM contracts WHERE id=? AND site_id=? AND customer_id=?",
                                        (contract_id, site_id, customer_id)).fetchone():
        raise ApiError(422, "invalid_contract", "Choose a contract of this site.")
    when = _iso(order_date, "Date") if order_date else db.reference_now().date()
    n = _next(conn, "orders", customer_id, "OP")
    oid = f"{customer_id}-OP{n}"
    conn.execute("INSERT INTO orders(id,customer_id,site_id,contract_id,container,date,status,reference,source,created_by,created_at) "
                 "VALUES(?,?,?,?,?,?,'in_progress',?,'poc_added',?,?)",
                 (oid, customer_id, site_id, contract_id or None, box["number"], when.isoformat(),
                  f"ORD-{_suffix(cust)}-P{n}", actor["id"], db.now()))
    _stamp(conn, actor, "order", oid, {"site": site_id, "container": box["number"]})
    conn.commit()
    return dict(conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())


def add_customer(conn, actor: dict, name: str, postcode: str | None, first_site: str | None) -> dict:
    """Add a customer with the next customer number (and optionally a first site so it can be used at once).

    Several customers may share a name (the seed has two "Delta Works"), so duplicates are allowed.
    """
    name = _clean(name, "name", 2, 120)
    postcode = (postcode or "").strip()
    if postcode and not _POSTCODE.match(postcode):
        raise ApiError(422, "invalid_postcode", "Postcode must look like 1234 AB.")
    first_site = _clean(first_site, "site_name", 2, 80) if (first_site or "").strip() else None
    last = conn.execute("SELECT max(CAST(number AS INTEGER)) FROM customers").fetchone()[0] or 100000
    num = int(last) + 1
    cid = f"C{num - 100000:03d}"
    while conn.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone():
        num += 1
        cid = f"C{num - 100000:03d}"
    conn.execute("INSERT INTO customers(id,number,name,postcode,active,created_at,source,created_by) "
                 "VALUES(?,?,?,?,1,?,'poc_added',?)",
                 (cid, str(num), name, postcode.replace(" ", "").upper() or None, db.now(), actor["id"]))
    _stamp(conn, actor, "customer", cid, {"number": str(num)})
    conn.commit()
    if first_site:
        add_site(conn, actor, cid, first_site, postcode or None)
    return dict(conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone())


def _like(q: str) -> str:
    return "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_customers(conn, q: str | None, limit: int, offset: int) -> dict:
    """Every customer with how much data each has (for the Customers page)."""
    where, args = "", []
    if q and q.strip():
        where = "WHERE lower(c.name) LIKE ? ESCAPE '\\' OR c.number LIKE ?"
        args = [_like(q.strip()), q.strip() + "%"]
    total = conn.execute(f"SELECT count(*) FROM customers c {where}", args).fetchone()[0]
    rows = conn.execute(
        "SELECT c.id, c.number, c.name, c.postcode, c.source, "
        "(SELECT count(*) FROM sites x WHERE x.customer_id=c.id) AS sites, "
        "(SELECT count(*) FROM contracts x WHERE x.customer_id=c.id) AS contracts, "
        "(SELECT count(*) FROM orders x WHERE x.customer_id=c.id) AS orders, "
        "(SELECT count(*) FROM containers x WHERE x.customer_id=c.id) AS containers "
        f"FROM customers c {where} ORDER BY c.name, c.number LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# section -> (FROM clause, columns, searchable expressions, ORDER BY). Fixed text only: nothing user-supplied is interpolated.
_ROWS = {
    "sites": ("sites t JOIN customers c ON c.id=t.customer_id", "t.*", ["lower(t.name)", "lower(t.reference)"], "c.name, t.id"),
    "contracts": ("contracts t JOIN customers c ON c.id=t.customer_id LEFT JOIN sites s ON s.id=t.site_id",
                  "t.*, s.name AS site_name", ["lower(t.reference)"], "c.name, t.id"),
    "orders": ("orders t JOIN customers c ON c.id=t.customer_id LEFT JOIN sites s ON s.id=t.site_id",
               "t.*, s.name AS site_name", ["lower(t.reference)", "lower(t.container)"], "t.date DESC, t.id"),
    "containers": ("containers t JOIN customers c ON c.id=t.customer_id LEFT JOIN sites s ON s.id=t.site_id",
                   "t.*, s.name AS site_name", ["lower(t.number)"], "c.name, t.number"),
}


def list_rows(conn, section: str, customer_id: str | None, q: str | None, limit: int, offset: int) -> dict:
    """Rows of one kind across all customers (or one), each with its customer's name and number."""
    if section not in _ROWS:
        raise ApiError(404, "unknown_section", "Unknown section.")
    source, cols, searchable, order = _ROWS[section]
    clauses, args = [], []
    if customer_id:
        clauses.append("t.customer_id=?")
        args.append(customer_id)
    if q and q.strip():
        clauses.append("(" + " OR ".join(f"{e} LIKE ? ESCAPE '\\'" for e in searchable) + ")")
        args += [_like(q.strip())] * len(searchable)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = conn.execute(f"SELECT count(*) FROM {source} {where}", args).fetchone()[0]
    rows = conn.execute(f"SELECT {cols}, c.name AS customer_name, c.number AS customer_number FROM {source} {where} "
                        f"ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    items = [dict(r) for r in rows]
    if section == "contracts":
        for r in items:
            r["active"] = r["status"] == "active"
    return {"items": items, "total": total, "limit": limit, "offset": offset}
