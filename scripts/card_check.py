"""FR-03 check: what the search card shows for a customer matches the data (sites, active contracts, last 10 orders).

    python -m scripts.card_check [--n 20]     # read-only; uses the database the app is configured for

For each customer the card is read through the same search the app uses and compared with plain queries on the tables.
"""
import argparse
import sys

from backend import db
from backend.services import lookup


def check(conn, customers) -> list:
    """Return a list of mismatch descriptions (empty = every card matches the data)."""
    bad = []
    for c in customers:
        res = lookup.search(conn, c["number"])
        if res["count"] != 1 or res["candidates"][0]["customer_id"] != c["id"]:
            bad.append(f"{c['number']}: search did not return exactly this customer")
            continue
        card = res["candidates"][0]
        sites = [tuple(r) for r in conn.execute("SELECT id,name,postcode FROM sites WHERE customer_id=? ORDER BY id", (c["id"],))]
        if [(x["id"], x["name"], x["postcode"]) for x in card["sites"]] != sites:
            bad.append(f"{c['number']}: sites differ")
        contracts = {r[0]: r[1] == "active" for r in conn.execute("SELECT reference,status FROM contracts WHERE customer_id=?", (c["id"],))}
        if {k["reference"]: k["active"] for k in card["contracts"]} != contracts:
            bad.append(f"{c['number']}: contracts or their active flag differ")
        orders = [tuple(r) for r in conn.execute(
            "SELECT reference,container,substr(date,1,10),status,site_id FROM orders WHERE customer_id=? ORDER BY date DESC, id DESC LIMIT 10", (c["id"],))]
        shown = [(o["reference"], o["container"], o["date"], o["status"], o["site_id"]) for o in card["recent_orders"]]
        if shown != orders:
            bad.append(f"{c['number']}: last orders differ")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    n = ap.parse_args().n
    with db.connect() as conn:
        customers = [dict(r) for r in conn.execute("SELECT id,number FROM customers WHERE source='seed' ORDER BY number LIMIT ?", (n,))]
        bad = check(conn, customers)
    for line in bad:
        print("MISMATCH", line)
    print(f"{len(customers) - len({b.split(':')[0] for b in bad})} of {len(customers)} customers show exactly what the data holds")
    return 1 if bad or len(customers) < n else 0


if __name__ == "__main__":
    sys.exit(main())
