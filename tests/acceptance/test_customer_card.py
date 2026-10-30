"""FR-03: the card after a match shows the customer's sites, active contracts and last 10 orders, as in the data (20 customers)."""
from backend import db
from backend.services import lookup
from scripts.card_check import check


def test_twenty_customers_show_exactly_what_the_data_holds(client):
    with db.connect() as conn:
        customers = [dict(r) for r in conn.execute("SELECT id,number FROM customers WHERE source='seed' ORDER BY number LIMIT 20")]
        assert len(customers) == 20
        assert check(conn, customers) == []


def test_a_card_that_differs_from_the_data_is_reported(client, monkeypatch):
    real = lookup.search

    def shortened(conn, q):                       # a card with its newest order missing and a contract wrongly active
        out = real(conn, q)
        card = out["candidates"][0]
        card["recent_orders"] = card["recent_orders"][1:]
        card["contracts"][0]["active"] = not card["contracts"][0]["active"]
        return out

    monkeypatch.setattr(lookup, "search", shortened)
    with db.connect() as conn:
        c = dict(conn.execute("SELECT id,number FROM customers WHERE source='seed' ORDER BY number LIMIT 1").fetchone())
        problems = " ".join(check(conn, [c]))
    assert "last orders differ" in problems and "contracts" in problems


def test_the_card_has_ten_orders_across_sites_and_all_contracts(client):
    card = client.get("/api/customers/search", params={"q": "100009"}, headers={"X-Demo-User": "demo.emp.a1"}).json()["candidates"][0]
    assert len(card["recent_orders"]) == 10 and {o["site_id"] for o in card["recent_orders"]} >= {"C009-S1"}
    assert [k["active"] for k in card["contracts"]].count(True) >= 1
