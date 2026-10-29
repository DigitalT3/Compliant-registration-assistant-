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


# ---- real administrator: created from the command line, creates people, resets passwords ----

def bearer(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["user"]


def test_demo_accounts_are_off_unless_switched_on(client, monkeypatch):
    monkeypatch.delenv("POC_DEMO_MODE", raising=False)
    assert client.get("/api/auth/me", headers=EMP).status_code == 401
    assert client.get("/api/auth/options").json()["demo_mode"] is False


def test_first_admin_is_created_from_the_command_line_and_can_run_the_system(client, monkeypatch):
    from backend import admin
    monkeypatch.setenv("POC_ADMIN_PASSWORD", "operator-password-1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert admin.main(["create-admin", "--email", "Boss@Example.nl", "--name", "Ada Admin"]) == 0
    h, user = bearer(client, "boss@example.nl", "operator-password-1")
    assert user["role"] == "admin" and user["must_change_password"] in (0, False)
    uid = register(client).json()["id"]                                     # a person signs themselves up
    pending = client.get("/api/users", headers=h, params={"status": "pending"}).json()["items"]
    assert [p["id"] for p in pending] == [uid]
    assert client.patch(f"/api/users/{uid}", headers=h, json={"status": "active"}).status_code == 200
    assert login(client).status_code == 200                                 # no demo account was involved


def test_admin_creates_a_person_with_a_one_time_password_that_must_be_changed(client):
    r = client.post("/api/users", headers=ADMIN, json={"name": "Joost Bakker", "email": "joost@example.nl",
                                                        "function": "customer_service"})
    assert r.status_code == 201
    temp = r.json()["temporary_password"]
    assert len(temp) >= 12 and r.json()["user"]["role"] == "employee"
    h, user = bearer(client, "joost@example.nl", temp)
    assert user["must_change_password"] in (1, True)
    blocked = client.get("/api/customers/search", params={"q": "100009"}, headers=h)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/api/auth/me", headers=h).status_code == 200          # still allowed: needed to show the screen
    bad = client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong-one-123", "new_password": "a-brand-new-pw-1"})
    assert bad.status_code == 403 and bad.json()["error"]["code"] == "wrong_password"
    weak = client.post("/api/auth/change-password", headers=h, json={"current_password": temp, "new_password": "short"})
    assert weak.json()["error"]["code"] == "weak_password"
    same = client.post("/api/auth/change-password", headers=h, json={"current_password": temp, "new_password": temp})
    assert same.json()["error"]["code"] == "same_password"
    ok = client.post("/api/auth/change-password", headers=h, json={"current_password": temp, "new_password": "a-brand-new-pw-1"})
    assert ok.status_code == 200 and ok.json()["user"]["must_change_password"] in (0, False)
    new = {"Authorization": "Bearer " + ok.json()["token"]}
    assert client.get("/api/customers/search", params={"q": "100009"}, headers=new).status_code == 200
    assert client.get("/api/auth/me", headers=h).json()["error"]["code"] == "session_expired"   # the old session ended
    assert client.post("/api/auth/login", json={"email": "joost@example.nl", "password": temp}).status_code == 401


def test_admin_reset_unlocks_and_issues_a_new_temporary_password(client):
    approve(client, register(client).json()["id"])
    for _ in range(5):
        login(client, password="wrong-password-1")
    assert login(client).status_code == 429
    uid = next(u["id"] for u in client.get("/api/users", headers=ADMIN).json()["items"] if u["email"] == NEW["email"].lower())
    temp = client.post(f"/api/users/{uid}/reset-password", headers=ADMIN).json()["temporary_password"]
    assert login(client).status_code == 401                                   # old password no longer works
    assert login(client, password=temp).json()["user"]["must_change_password"] in (1, True)
    assert client.post("/api/users/demo.emp.a1/reset-password", headers=ADMIN).json()["error"]["code"] == "no_password_login"
    assert client.post(f"/api/users/{uid}/reset-password", headers=EMP).status_code == 403


def test_only_admins_create_people_and_input_is_validated(client):
    body = {"name": "X Person", "email": "x@example.nl", "function": "sales"}
    assert client.post("/api/users", headers=EMP, json=body).status_code == 403
    assert client.post("/api/users", headers=ADMIN, json={**body, "role": "wizard"}).json()["error"]["code"] == "invalid_role"
    assert client.post("/api/users", headers=ADMIN, json={**body, "function": "nope"}).json()["error"]["code"] == "invalid_function"
    assert client.post("/api/users", headers=ADMIN, json=body).status_code == 201
    assert client.post("/api/users", headers=ADMIN, json=body).json()["error"]["code"] == "email_taken"
    with db.connect() as conn:
        acts = [r["action"] for r in conn.execute("SELECT action FROM audit")]
    assert "account_created" in acts
