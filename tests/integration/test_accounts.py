"""Employee accounts: registration with a function category, sign-in, approval, lockout, roles."""
import time

from backend import db
from backend.services import accounts
from tests.conftest import ADMIN, EMP

NEW = {"name": "Sanne de Vries", "email": "Sanne.DeVries@Example.nl", "password": "correct-horse-9", "function": "sales"}


def register(client, **over):
    return client.post("/api/auth/register", json={**NEW, **over})


def login(client, email=NEW["email"], password=NEW["password"]):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def approve(client, uid, **body):
    return client.patch(f"/api/users/{uid}", headers=ADMIN, json={"status": "active", **body})


def test_options_list_the_three_function_categories(client):
    o = client.get("/api/auth/options").json()
    assert [f["id"] for f in o["functions"]] == ["customer_service", "sales", "site_operations"]
    assert o["require_approval"] is True and o["min_password_length"] >= 10


def test_registration_creates_a_pending_employee_with_a_hashed_password(client):
    r = register(client)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE lower(email)=?", (NEW["email"].lower(),)).fetchone()
    assert (row["role"], row["function"], row["user_group"], row["status"]) == ("employee", "sales", "sales", "pending")
    assert row["password_hash"].startswith("scrypt$") and NEW["password"] not in row["password_hash"]


def test_registration_validation(client):
    assert register(client, function="astronaut").json()["error"]["code"] == "invalid_function"
    assert register(client, email="not-an-email").json()["error"]["code"] == "invalid_email"
    assert register(client, password="short").json()["error"]["code"] == "weak_password"
    assert register(client, name=" ").json()["error"]["code"] == "invalid_name"
    assert register(client).status_code == 201
    assert register(client, email="sanne.devries@example.nl").json()["error"]["code"] == "email_taken"


def test_pending_account_cannot_sign_in_until_approved(client):
    uid = register(client).json()["id"]
    r = login(client)
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_pending"
    assert approve(client, uid).status_code == 200
    ok = login(client).json()
    assert ok["user"]["role"] == "employee" and ok["user"]["function"] == "sales"
    assert set(ok["user"]["permissions"]) == {"register", "read"} and "password_hash" not in str(ok)


def test_wrong_password_is_generic_and_does_not_reveal_accounts(client):
    uid = register(client).json()["id"]
    approve(client, uid)
    a = login(client, password="wrong-password-1").json()["error"]
    b = login(client, email="nobody@example.nl").json()["error"]
    assert a["code"] == b["code"] == "invalid_credentials" and a["message"] == b["message"]


def test_lockout_after_repeated_failures(client):
    approve(client, register(client).json()["id"])
    for _ in range(5):
        assert login(client, password="wrong-password-1").status_code == 401
    r = login(client)                                   # even the right password is refused while locked
    assert r.status_code == 429 and r.json()["error"]["code"] == "account_locked"


def test_token_authenticates_and_role_comes_from_the_database(client):
    uid = register(client).json()["id"]
    approve(client, uid)
    h = {"Authorization": "Bearer " + login(client).json()["token"]}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["id"] == uid and me["function"] == "sales"
    assert client.get("/api/customers/search", params={"q": "100009"}, headers=h).status_code == 200
    assert client.get("/api/analytics/summary", headers=h).status_code == 403       # employees have no analytics
    assert client.get("/api/users", headers=h).status_code == 403
    client.patch(f"/api/users/{uid}", headers=ADMIN, json={"role": "lead"})
    assert client.get("/api/analytics/summary", headers=h).status_code == 200       # same token, new role


def test_invalid_expired_and_disabled(client, monkeypatch):
    uid = register(client).json()["id"]
    approve(client, uid)
    token = login(client).json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token + "x"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    client.patch(f"/api/users/{uid}", headers=ADMIN, json={"status": "disabled"})
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 401 and r.json()["error"]["code"] == "account_inactive"
    assert login(client).json()["error"]["code"] == "account_disabled"
    client.patch(f"/api/users/{uid}", headers=ADMIN, json={"status": "active"})
    real = time.time()
    monkeypatch.setattr(accounts.time, "time", lambda: real + 9 * 3600)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).json()["error"]["code"] == "session_expired"


def test_demo_header_works_only_in_demo_mode(client, monkeypatch):
    assert client.get("/api/auth/me", headers=EMP).json()["id"] == "demo.emp.a1"
    monkeypatch.setenv("POC_DEMO_MODE", "0")
    assert client.get("/api/auth/me", headers=EMP).status_code == 401
    assert client.get("/api/auth/options").json()["demo_mode"] is False


def test_admin_rules(client):
    users = client.get("/api/users", headers=ADMIN).json()["items"]
    assert any(u["id"] == "demo.admin" for u in users)
    assert client.get("/api/users", headers=EMP).status_code == 403
    assert client.patch("/api/users/demo.admin", headers=ADMIN, json={"status": "disabled"}).status_code == 409
    assert client.patch("/api/users/demo.emp.a1", headers=ADMIN, json={"role": "wizard"}).status_code == 422
    assert client.patch("/api/users/nobody", headers=ADMIN, json={"status": "active"}).status_code == 404
    pending = client.get("/api/users", headers=ADMIN, params={"status": "pending"}).json()["items"]
    assert pending == []


def test_registered_employee_registers_a_complaint_as_themselves(client):
    uid = register(client).json()["id"]
    approve(client, uid)
    h = {"Authorization": "Bearer " + login(client).json()["token"]}
    r = client.post("/api/complaints", headers=h, json={"customer_id": "C009", "site_id": "C009-S1", "channel": "phone",
                    "complaint_type": "service", "root_cause": "missed", "description": "Container missed."})
    assert r.status_code == 201
    assert client.get(f"/api/complaints/{r.json()['id']}", headers=h).json()["registering_user"] == uid
    with db.connect() as conn:
        actions = [x["action"] for x in conn.execute("SELECT action FROM audit WHERE actor=?", (uid,))]
    assert {"account_registered", "login", "complaint_saved"} <= set(actions)
