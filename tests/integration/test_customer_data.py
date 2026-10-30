"""Adding sites, contracts, containers and orders for an existing customer (PoC customer data)."""
from backend import db
from tests.conftest import ADMIN, EMP

LEAD = {"X-Demo-User": "demo.lead"}
VIEWER = {"X-Demo-User": "demo.viewer"}
C = "/api/customers/C009"


def ctx(client, **params):
    return client.get(f"{C}/context", headers=EMP, params=params).json()


def test_containers_are_records_and_part_of_the_context(client):
    boxes = ctx(client)["containers"]
    assert {b["number"] for b in boxes} == {"BOX-009-1", "BOX-009-2"}
    assert all(b["source"] == "seed" for b in boxes)
    with db.connect() as conn:                                  # one container per seeded site
        assert conn.execute("SELECT count(*) FROM containers").fetchone()[0] == conn.execute("SELECT count(*) FROM sites").fetchone()[0]


def test_only_roles_with_customer_data_may_add(client):
    for who in (LEAD, VIEWER):
        assert client.post(f"{C}/sites", headers=who, json={"name": "Nope depot"}).status_code == 403
    assert client.post(f"{C}/sites", json={"name": "Nope depot"}).status_code == 401
    assert client.post(f"{C}/sites", headers=EMP, json={"name": "Synthetic depot 3", "postcode": "1009 ZZ"}).status_code == 201
    assert client.post(f"{C}/sites", headers=ADMIN, json={"name": "Synthetic depot 4"}).status_code == 201


def test_add_site_then_it_appears_in_the_context_marked_as_added_in_the_poc(client):
    r = client.post(f"{C}/sites", headers=EMP, json={"name": "  Synthetic   depot 3 ", "postcode": "1009 zz"})
    site = r.json()
    assert (site["id"], site["reference"], site["name"], site["postcode"]) == ("C009-S3", "SITE-009-3", "Synthetic depot 3", "1009ZZ")
    assert (site["source"], site["created_by"]) == ("poc_added", "demo.emp.a1")
    assert [s["id"] for s in ctx(client)["sites"]] == ["C009-S1", "C009-S2", "C009-S3"]
    assert client.post(f"{C}/sites", headers=EMP, json={"name": "x"}).json()["error"]["code"] == "invalid_name"
    assert client.post(f"{C}/sites", headers=EMP, json={"name": "Okay depot", "postcode": "99"}).json()["error"]["code"] == "invalid_postcode"
    assert client.post("/api/customers/NOPE/sites", headers=EMP, json={"name": "Okay depot"}).status_code == 404


def test_add_container_contract_and_order_for_the_new_site(client):
    site = client.post(f"{C}/sites", headers=EMP, json={"name": "Synthetic depot 3"}).json()["id"]
    box = client.post(f"{C}/containers", headers=EMP, json={"site_id": site}).json()          # number generated
    assert box["number"] == "BOX-009-3" and box["site_id"] == site and box["source"] == "poc_added"
    own = client.post(f"{C}/containers", headers=EMP, json={"site_id": site, "number": "bin-77x"}).json()
    assert own["number"] == "BIN-77X"
    contract = client.post(f"{C}/contracts", headers=EMP, json={"site_id": site, "valid_from": "2026-10-01", "valid_to": "2027-09-30"}).json()
    assert (contract["id"], contract["reference"], contract["status"], contract["active"]) == ("C009-K3", "CON-009-3", "active", True)
    order = client.post(f"{C}/orders", headers=EMP, json={"site_id": site, "container": "box-009-3", "contract_id": contract["id"]}).json()
    assert (order["reference"], order["container"], order["contract_id"], order["source"]) == ("ORD-009-P1", "BOX-009-3", "C009-K3", "poc_added")
    c = ctx(client)
    assert c["orders"][0]["id"] == order["id"]                                                   # newest first
    assert {b["number"] for b in c["containers"]} >= {"BOX-009-3", "BIN-77X"}


def test_new_data_feeds_the_registration_prefill(client):
    site = client.post(f"{C}/sites", headers=EMP, json={"name": "Synthetic depot 3"}).json()["id"]
    box = client.post(f"{C}/containers", headers=EMP, json={"site_id": site}).json()["number"]
    k = client.post(f"{C}/contracts", headers=EMP, json={"site_id": site}).json()["id"]
    o = client.post(f"{C}/orders", headers=EMP, json={"site_id": site, "container": box, "contract_id": k}).json()["id"]
    f = client.post("/api/prefill", headers=EMP, json={"customer_id": "C009", "site_id": site}).json()["fields"]
    assert (f["site_id"]["value"], f["contract_id"]["value"], f["order_id"]["value"], f["container"]["value"]) == (site, k, o, box)


def test_ownership_and_validation(client):
    other_site = "C001-S1"                                                   # a site of another customer
    assert client.post(f"{C}/contracts", headers=EMP, json={"site_id": other_site}).json()["error"]["code"] == "invalid_site"
    assert client.post(f"{C}/containers", headers=EMP, json={"site_id": "nope"}).json()["error"]["code"] == "invalid_site"
    assert client.post(f"{C}/containers", headers=EMP, json={"site_id": "C009-S1", "number": "BOX-009-1"}).status_code == 409
    assert client.post(f"{C}/containers", headers=EMP, json={"site_id": "C009-S1", "number": "box-009-1"}).status_code == 409   # case-insensitive
    assert client.post(f"{C}/containers", headers=EMP, json={"site_id": "C009-S1", "number": "a b"}).json()["error"]["code"] == "invalid_container"
    assert client.post(f"{C}/contracts", headers=EMP, json={"site_id": "C009-S1", "valid_from": "2027-01-01", "valid_to": "2026-01-01"}).json()["error"]["code"] == "invalid_dates"
    assert client.post(f"{C}/contracts", headers=EMP, json={"site_id": "C009-S1", "valid_from": "yesterday"}).json()["error"]["code"] == "invalid_date"
    # an order needs a container of the same site, and a contract of the same site
    assert client.post(f"{C}/orders", headers=EMP, json={"site_id": "C009-S1", "container": "BOX-009-2"}).json()["error"]["code"] == "invalid_container"
    assert client.post(f"{C}/orders", headers=EMP, json={"site_id": "C009-S1", "container": "BOX-009-1", "contract_id": "C009-K2"}).json()["error"]["code"] == "invalid_contract"
    assert client.post(f"{C}/orders", headers=EMP, json={"site_id": "C009-S1", "container": "BOX-001-1"}).json()["error"]["code"] == "invalid_container"
    assert client.post(f"{C}/orders", headers=EMP, json={"site_id": "C009-S1", "container": "BOX-009-1"}).status_code == 201


def test_an_expired_contract_is_stored_as_expired(client):
    r = client.post(f"{C}/contracts", headers=EMP, json={"site_id": "C009-S1", "valid_from": "2020-01-01", "valid_to": "2021-01-01"}).json()
    assert (r["status"], r["active"]) == ("expired", False)


def test_additions_are_audited_and_a_new_container_is_searchable(client):
    box = client.post(f"{C}/containers", headers=EMP, json={"site_id": "C009-S2", "number": "NEW-CONTAINER-1"}).json()["number"]
    with db.connect() as conn:
        rows = conn.execute("SELECT actor,action FROM audit WHERE action='customer_data_added'").fetchall()
    assert [(r["actor"], r["action"]) for r in rows] == [("demo.emp.a1", "customer_data_added")]
    found = client.get("/api/customers/search", headers=EMP, params={"q": box.lower()}).json()      # no order exists for it yet
    assert found["match_type"] == "container" and found["candidates"][0]["customer_id"] == "C009"
    assert found["candidates"][0]["matched_site_id"] == "C009-S2"


def test_all_orders_on_request(client):
    for _ in range(12):
        client.post(f"{C}/orders", headers=EMP, json={"site_id": "C009-S1", "container": "BOX-009-1"})
    assert len(ctx(client)["orders"]) == 10
    assert len(ctx(client, all="true")["orders"]) > 10


# ---- all customers, and adding a customer ----

def test_add_customer_takes_the_next_number_and_can_get_a_first_site(client):
    r = client.post("/api/customers", headers=EMP, json={"name": "  Nieuwe   Klant BV ", "postcode": "3511 ab", "first_site": "Hoofdlocatie"})
    assert r.status_code == 201
    c = r.json()
    assert (c["id"], c["number"], c["name"], c["postcode"], c["source"], c["created_by"]) == (
        "C035", "100035", "Nieuwe Klant BV", "3511AB", "poc_added", "demo.emp.a1")
    ctx_ = client.get("/api/customers/C035/context", headers=EMP).json()
    assert [(s["id"], s["name"], s["source"]) for s in ctx_["sites"]] == [("C035-S1", "Hoofdlocatie", "poc_added")]
    found = client.get("/api/customers/search", headers=EMP, params={"q": "100035"}).json()       # usable at once
    assert found["match_type"] == "customer_number" and found["candidates"][0]["name"] == "Nieuwe Klant BV"
    second = client.post("/api/customers", headers=EMP, json={"name": "Nieuwe Klant BV"}).json()   # same name is allowed
    assert second["number"] == "100036" and client.get("/api/customers/C036/context", headers=EMP).json()["sites"] == []


def test_add_customer_validation_and_permission(client):
    assert client.post("/api/customers", headers=LEAD, json={"name": "Nope BV"}).status_code == 403
    assert client.post("/api/customers", json={"name": "Nope BV"}).status_code == 401
    assert client.post("/api/customers", headers=EMP, json={"name": "x"}).json()["error"]["code"] == "invalid_name"
    assert client.post("/api/customers", headers=EMP, json={"name": "Fine BV", "postcode": "12"}).json()["error"]["code"] == "invalid_postcode"
    bad = client.post("/api/customers", headers=EMP, json={"name": "Fine BV", "first_site": "x"})
    assert bad.json()["error"]["code"] == "invalid_site_name"
    assert client.get("/api/customers", headers=EMP).json()["total"] == 34                       # nothing half-created
    with db.connect() as conn:
        assert conn.execute("SELECT action FROM audit WHERE action='customer_data_added'").fetchone() is None


def test_customers_list_has_counts_search_and_paging(client):
    page = client.get("/api/customers", headers=EMP).json()
    assert page["total"] == 34 and len(page["items"]) == 34 and page["limit"] == 50
    one = next(i for i in page["items"] if i["number"] == "100009")
    assert (one["name"], one["sites"], one["contracts"], one["containers"], one["source"]) == ("Zorgcentrum Het Anker", 2, 2, 2, "seed")
    assert one["orders"] > 0
    delta = client.get("/api/customers", headers=EMP, params={"q": "delta works"}).json()
    assert delta["total"] == 2 and all("Delta Works" in i["name"] for i in delta["items"])
    assert client.get("/api/customers", headers=EMP, params={"q": "10001"}).json()["total"] >= 9          # number prefix
    p2 = client.get("/api/customers", headers=EMP, params={"limit": 10, "offset": 10}).json()
    assert len(p2["items"]) == 10 and p2["total"] == 34
    assert client.get("/api/customers", headers=LEAD).status_code == 403
    assert client.get("/api/customers", headers=EMP, params={"limit": 999}).status_code == 422


def test_rows_across_all_customers_with_filter_search_and_customer_columns(client):
    sites = client.get("/api/customer-data/sites", headers=EMP).json()
    assert sites["total"] == 68 and {"customer_name", "customer_number", "reference"} <= set(sites["items"][0])
    assert len({s["customer_id"] for s in sites["items"]}) > 20                                      # many customers at once
    mine = client.get("/api/customer-data/sites", headers=EMP, params={"customer_id": "C009"}).json()
    assert mine["total"] == 2 and {s["customer_number"] for s in mine["items"]} == {"100009"}
    hit = client.get("/api/customer-data/sites", headers=EMP, params={"q": "site-009"}).json()
    assert hit["total"] == 2
    contracts = client.get("/api/customer-data/contracts", headers=EMP, params={"customer_id": "C009"}).json()["items"]
    assert [(c["reference"], c["site_name"], c["active"]) for c in contracts] == [("CON-009-1", "Synthetic depot 1", True), ("CON-009-2", "Synthetic depot 2", True)]
    orders = client.get("/api/customer-data/orders", headers=EMP, params={"customer_id": "C009", "limit": 5}).json()
    assert len(orders["items"]) == 5 and orders["total"] > 5
    assert [o["date"] for o in orders["items"]] == sorted((o["date"] for o in orders["items"]), reverse=True)    # newest first
    assert client.get("/api/customer-data/containers", headers=EMP, params={"q": "box-009-2"}).json()["total"] == 1
    assert client.get("/api/customer-data/nonsense", headers=EMP).status_code == 422
    assert client.get("/api/customer-data/sites", headers=VIEWER).status_code == 403
    assert client.get("/api/customer-data/sites", headers=EMP, params={"q": "%"}).json()["total"] == 0   # wildcards are not injected


# ---- the result card shows the contract and the recent orders (PRD step 1) ----

def search(client, q):
    return client.get("/api/customers/search", headers=EMP, params={"q": q}).json()


def test_result_card_has_contracts_and_the_ten_latest_orders(client):
    card = search(client, "100009")["candidates"][0]
    assert [(c["reference"], c["active"], c["valid_to"]) for c in card["contracts"]] == [
        ("CON-009-1", True, "2027-08-24"), ("CON-009-2", True, "2027-08-24")]
    assert len(card["recent_orders"]) == 10
    dates = [o["date"] for o in card["recent_orders"]]
    assert dates == sorted(dates, reverse=True) and {"reference", "container", "status"} <= set(card["recent_orders"][0])


def test_card_shows_the_customers_orders_over_all_sites_and_flags_expired_contracts(client):
    by_order = search(client, "ORD-002-10")["candidates"][0]
    assert len(by_order["recent_orders"]) == 10 and {o["site_id"] for o in by_order["recent_orders"]} >= {by_order["matched_site_id"]}   # the customer's, not only that site's
    expired = search(client, "100021")["candidates"][0]                                         # the seeded expired-contract customer
    assert [c["active"] for c in expired["contracts"]] == [False]


def test_broad_searches_skip_the_extra_detail(client):
    many = search(client, "a")                                    # matches many customers
    assert many["count"] > 5 and all("contracts" not in c for c in many["candidates"])
    few = search(client, "Delta Works")
    assert few["count"] == 2 and all("contracts" in c and "recent_orders" in c for c in few["candidates"])
