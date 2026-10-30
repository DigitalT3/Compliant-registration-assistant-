"""FR-04: customer, site, contract, order, channel, date and registering user are prefilled when a match exists; each can be edited."""
from datetime import date, timedelta

from backend import db
from backend.services import prefill
from tests.conftest import ADMIN, EMP

FIELDS = ("customer_id", "site_id", "contract_id", "order_id", "container", "channel", "registration_date", "registering_user")


def _numbers(n=20):
    with db.connect() as conn:
        return [r[0] for r in conn.execute("SELECT number FROM customers WHERE source='seed' ORDER BY number LIMIT ?", (n,))]


def _fields(client, q, origin="search"):
    c = client.get("/api/customers/search", params={"q": q}, headers=EMP).json()["candidates"][0]
    return client.post("/api/prefill", headers=EMP, json={
        "customer_id": c["customer_id"], "site_id": c["matched_site_id"], "order_id": c["matched_order_id"],
        "origin": origin, "guess_site": True}).json()["fields"]


def test_every_prefillable_field_is_filled_for_twenty_customers(client):
    numbers = _numbers()
    assert len(numbers) == 20
    for q in numbers:
        f = _fields(client, q)
        blank = [k for k in FIELDS if not f[k]["value"]]
        assert blank == [], f"{q}: not filled: {blank}"
        assert all(f[k]["provenance"] in ("prefilled", "default") for k in FIELDS)


def test_the_same_when_the_match_came_from_an_order_or_a_container(client):
    for q in ("ORD-002-10", "BOX-004-1", "ORD-030-10"):
        f = _fields(client, q)
        assert all(f[k]["value"] for k in FIELDS), q
    assert _fields(client, "ORD-002-10")["order_id"]["value"] == "C002-O10"        # the matched order wins over the latest


def test_the_site_follows_the_latest_order_when_the_search_gave_none(client):
    f = _fields(client, "100009")
    assert f["site_id"]["value"] == "C009-S1" and f["order_id"]["value"] == "C009-O10" and f["container"]["value"] == "BOX-009-1"
    assert f["contract_id"]["value"].startswith("C009")                              # the active contract of that site


def test_the_date_is_the_real_today_even_with_the_fixed_demo_clock(client):
    value = _fields(client, "100009")["registration_date"]["value"]
    assert value == prefill.today() and abs((date.fromisoformat(value) - date.today()).days) <= 1


def _body(client, **extra):
    c = client.get("/api/customers/search", params={"q": "100009"}, headers=EMP).json()["candidates"][0]
    return {"customer_id": c["customer_id"], "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
            "root_cause": "missed", "description": "Container not emptied.", **extra}


def test_the_date_and_the_registering_user_can_be_changed_and_are_saved(client):
    yesterday = (date.fromisoformat(prefill.today()) - timedelta(days=1)).isoformat()
    colleague = next(c for c in client.get("/api/users/colleagues", headers=EMP).json()["items"] if c["id"] != "demo.emp.a1")
    saved = client.post("/api/complaints", headers=EMP, json=_body(client, registration_date=yesterday, registering_user=colleague["id"]))
    assert saved.status_code == 201, saved.text
    rec = client.get(f"/api/complaints/{saved.json()['id']}", headers=EMP).json()
    assert rec["registration_date"] == yesterday and rec["registering_user"] == colleague["id"]
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit WHERE action='complaint_saved' AND data LIKE ?",
                            (f"%{colleague['id']}%",)).fetchone()[0] == 1       # registered on someone's behalf is traceable


def test_left_alone_they_are_today_and_the_signed_in_user(client):
    rec = client.get(f"/api/complaints/{client.post('/api/complaints', headers=EMP, json=_body(client)).json()['id']}", headers=EMP).json()
    assert rec["registration_date"] == prefill.today() and rec["registering_user"] == "demo.emp.a1"


def test_a_date_in_the_future_or_a_stranger_is_refused(client):
    tomorrow = (date.fromisoformat(prefill.today()) + timedelta(days=1)).isoformat()
    assert client.post("/api/complaints", headers=EMP, json=_body(client, registration_date=tomorrow)).json()["error"]["code"] == "invalid_registration_date"
    assert client.post("/api/complaints", headers=EMP, json=_body(client, registration_date="31-10-2026")).status_code == 422
    assert client.post("/api/complaints", headers=EMP, json=_body(client, registering_user="nobody")).json()["error"]["code"] == "invalid_registering_user"


def test_only_people_who_can_register_see_the_colleague_list(client):
    assert client.get("/api/users/colleagues", headers={"X-Demo-User": "demo.viewer"}).status_code == 403
    names = client.get("/api/users/colleagues", headers=ADMIN).json()["items"]
    assert names and set(names[0]) == {"id", "name"}                                  # names only


def test_with_demo_mode_off_only_real_accounts_can_be_the_registering_user(client, monkeypatch):
    from tests.integration.test_team_scope import signed_in
    eva = signed_in(client, "eva@example.nl", "customer_service")                           # a real account
    monkeypatch.setenv("POC_DEMO_MODE", "0")
    names = [c["name"] for c in client.get("/api/users/colleagues", headers=eva).json()["items"]]
    assert "Test Eva" in names and not any(n.startswith("Demo ") for n in names)
    body = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service", "root_cause": "missed", "description": "x"}
    assert client.post("/api/complaints", headers=eva, json={**body, "registering_user": "demo.emp.a1"}).json()["error"]["code"] == "invalid_registering_user"
