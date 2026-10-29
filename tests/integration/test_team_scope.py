"""Step 6 (Report): team leads see their own team only; accepted/changed tracking; Power BI export; idle cap."""
import csv
import io

from backend import db
from backend.services import sessions as sessions_svc
from tests.conftest import ADMIN, EMP
from tests.integration.test_step4_usertest import EVAL, LEAD, register

B1 = {"X-Demo-User": "demo.emp.b1"}          # group_b employee; the demo lead leads group_a
PROV = {"complaint_type": "suggested", "root_cause": "edited", "summary": "edited", "description": "manual",
        "channel": "default", "container": "blank", "site_id": "prefilled"}


def rows(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def two_teams(client):
    register(client, headers=EMP, participant="PA", field_provenance=PROV)
    register(client, headers=B1, participant="PB", field_provenance=PROV)


def test_lead_sees_only_the_team_they_lead(client):
    two_teams(client)
    admin = client.get("/api/analytics/summary", headers=ADMIN).json()
    assert admin["sessions"]["started"] == 2 and "scope" not in admin                 # admins see every team
    assert client.get("/api/analytics/summary", headers=EVAL).json()["sessions"]["started"] == 2
    lead = client.get("/api/analytics/summary", headers=LEAD).json()
    assert lead["sessions"]["started"] == 1 and lead["scope"] == {"team": "group_a"}
    forced = client.get("/api/analytics/summary", headers=LEAD, params={"group": "group_b"}).json()
    assert forced["sessions"]["started"] == 1 and forced["scope"]["team"] == "group_a"   # a team in the request is ignored
    assert "groups" not in client.get("/api/analytics/summary", headers=LEAD, params={"group_by": "group"}).json()
    items = client.get("/api/analytics/sessions", headers=LEAD, params={"group": "group_b"}).json()["items"]
    assert [i["user_group"] for i in items] == ["group_a"]
    assert {i["user_group"] for i in client.get("/api/analytics/sessions", headers=ADMIN).json()["items"]} == {"group_a", "group_b"}


def test_exports_follow_the_same_scope(client):
    two_teams(client)
    for url in ("/api/export/sessions.csv", "/api/export/suggestions.csv"):
        mine = rows(client.get(url, headers=LEAD, params={"group": "group_b"}))
        everyone = rows(client.get(url, headers=ADMIN))
        col = mine[0].index("group" if "sessions" in url else "team")
        assert {r[col] for r in mine[1:]} == {"group_a"}, url
        assert {r[col] for r in everyone[1:]} == {"group_a", "group_b"}, url


def test_suggestions_csv_labels_accepted_changed_typed_and_empty(client):
    two_teams(client)
    table = rows(client.get("/api/export/suggestions.csv", headers=ADMIN))
    assert table[0] == ["complaint_id", "session_id", "team", "user", "mode", "saved_at", "field", "origin", "outcome"]
    got = {(r[2], r[6]): (r[7], r[8]) for r in table[1:]}
    assert got[("group_a", "complaint_type")] == ("suggested", "accepted")
    assert got[("group_a", "summary")] == ("edited", "changed")
    assert got[("group_a", "root_cause")] == ("edited", "changed")
    assert got[("group_a", "description")] == ("manual", "typed")
    assert got[("group_a", "container")] == ("blank", "empty")
    assert got[("group_a", "channel")] == ("default", "accepted")
    assert client.get("/api/export/suggestions.csv", headers=EMP).status_code == 403


def test_a_lead_without_a_team_gets_nothing(client):
    two_teams(client)
    with db.connect() as conn:
        conn.execute("INSERT INTO users(id,name,role,user_group,function) VALUES('demo.lead.noteam','No Team','lead','leads',NULL)")
        conn.commit()
    h = {"X-Demo-User": "demo.lead.noteam"}
    for url in ("/api/analytics/summary", "/api/analytics/sessions", "/api/export/sessions.csv",
                "/api/export/suggestions.csv", "/api/analysis/other-reasons"):
        r = client.get(url, headers=h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "team_required", url


def test_other_reasons_for_a_lead_cover_their_team_only(client):
    before = client.get("/api/analysis/other-reasons", headers=ADMIN).json()["n"]        # includes seeded history (no team)
    register(client, headers=EMP, cause="other", other_reason="seagull nest")
    register(client, headers=B1, cause="other", other_reason="goat on the road")
    assert client.get("/api/analysis/other-reasons", headers=LEAD).json()["n"] == 1
    assert client.get("/api/analysis/other-reasons", headers=ADMIN).json()["n"] == before + 2


def test_a_lead_account_needs_a_team(client):
    body = {"name": "Anna Lead", "email": "anna.lead@example.nl", "role": "lead"}
    r = client.post("/api/users", headers=ADMIN, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "team_required"
    ok = client.post("/api/users", headers=ADMIN, json={**body, "function": "sales"})
    assert ok.status_code == 201 and ok.json()["user"]["function"] == "sales"
    uid = client.post("/api/users", headers=ADMIN, json={"name": "Emp Loyee", "email": "emp.loyee@example.nl", "role": "employee"}).json()["user"]["id"]
    r = client.patch(f"/api/users/{uid}", headers=ADMIN, json={"role": "lead"})              # promoting without a team
    assert r.status_code == 422 and r.json()["error"]["code"] == "team_required"
    done = client.patch(f"/api/users/{uid}", headers=ADMIN, json={"role": "lead", "function": "site_operations"}).json()
    assert done["role"] == "lead" and done["function"] == "site_operations" and done["user_group"] == "site_operations"
    assert client.patch(f"/api/users/{uid}", headers=ADMIN, json={"function": "nope"}).status_code == 422


def test_step_time_is_capped_per_visit():
    events = [{"event_type": "step_entered", "step": "classify", "at": "2026-10-29T08:00:00+00:00"},
              {"event_type": "step_entered", "step": "repeat_save", "at": "2026-10-29T13:00:00+00:00"},   # tab left open 5 h
              {"event_type": "step_completed", "step": "repeat_save", "at": "2026-10-29T13:00:30+00:00"}]
    got = sessions_svc.step_durations(events, None)
    assert got == {"classify": 600.0, "repeat_save": 30.0}                                   # default cap: 10 minutes
    assert sessions_svc.step_durations(events, None, cap=60)["classify"] == 60.0
    assert sessions_svc.step_durations(events, None, cap=0)["classify"] == 18000.0           # no cap


def signed_in(client, email, function=None, role="employee"):
    """Admin creates the account; the person signs in with the temporary password and chooses their own."""
    r = client.post("/api/users", headers=ADMIN, json={"name": "Test " + email.split("@")[0].title(), "email": email,
                                                        "function": function, "role": role})
    assert r.status_code == 201, r.text
    first = client.post("/api/auth/login", json={"email": email, "password": r.json()["temporary_password"]}).json()
    done = client.post("/api/auth/change-password", headers={"Authorization": "Bearer " + first["token"]},
                       json={"current_password": r.json()["temporary_password"], "new_password": "my-own-password-1"})
    assert done.status_code == 200, done.text
    return {"Authorization": "Bearer " + done.json()["token"]}


def test_a_real_lead_account_sees_only_their_team_end_to_end(client):
    """No demo headers: real accounts, temporary passwords, tokens."""
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    service = signed_in(client, "karel.service@example.nl", "customer_service")
    lead = signed_in(client, "lotte.lead@example.nl", "sales", role="lead")
    register(client, headers=sales, participant="S1", field_provenance=PROV)
    register(client, headers=service, participant="C1", field_provenance=PROV)

    me = client.get("/api/auth/me", headers=lead).json()
    assert me["role"] == "lead" and me["function"] == "sales"
    summary = client.get("/api/analytics/summary", headers=lead).json()
    assert summary["sessions"]["started"] == 1 and summary["scope"] == {"team": "sales"}
    assert {i["user_group"] for i in client.get("/api/analytics/sessions", headers=lead).json()["items"]} == {"sales"}
    for url, col in (("/api/export/sessions.csv", "group"), ("/api/export/suggestions.csv", "team")):
        table = rows(client.get(url, headers=lead, params={"group": "customer_service"}))
        assert {r[table[0].index(col)] for r in table[1:]} == {"sales"}, url
    assert client.post("/api/sessions", headers=lead, json={}).status_code == 403                          # leads do not register
    assert client.get("/api/users", headers=lead).status_code == 403
    everyone = client.get("/api/analytics/summary", headers=ADMIN).json()
    assert everyone["sessions"]["started"] == 2 and "scope" not in everyone


def test_changing_a_leads_team_takes_effect_on_their_next_request(client):
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    service = signed_in(client, "karel.service@example.nl", "customer_service")
    lead = signed_in(client, "lotte.lead@example.nl", "sales", role="lead")
    register(client, headers=sales, participant="S1")
    register(client, headers=service, participant="C1")
    assert client.get("/api/analytics/summary", headers=lead).json()["scope"]["team"] == "sales"
    lead_id = client.get("/api/auth/me", headers=lead).json()["id"]
    assert client.patch(f"/api/users/{lead_id}", headers=ADMIN, json={"function": "customer_service"}).status_code == 200
    moved = client.get("/api/analytics/summary", headers=lead).json()
    assert moved["scope"]["team"] == "customer_service" and moved["sessions"]["started"] == 1


def test_old_step_names_count_under_the_merged_step():
    events = [{"event_type": "step_entered", "step": "classify", "at": "2026-10-29T08:00:00+00:00"},
              {"event_type": "step_entered", "step": "check_repeats", "at": "2026-10-29T08:01:00+00:00"},    # recorded before the merge
              {"event_type": "step_entered", "step": "review_save", "at": "2026-10-29T08:01:20+00:00"},
              {"event_type": "step_completed", "step": "review_save", "at": "2026-10-29T08:02:00+00:00"}]
    assert sessions_svc.step_durations(events, None) == {"classify": 60.0, "repeat_save": 60.0}               # 20 s + 40 s


def test_the_cap_is_per_visit_so_repeated_visits_add_up():
    events = [{"event_type": "step_entered", "step": "review_details", "at": "2026-10-29T08:00:00+00:00"},
              {"event_type": "step_entered", "step": "describe_complaint", "at": "2026-10-29T09:00:00+00:00"},   # 1 h idle
              {"event_type": "step_entered", "step": "review_details", "at": "2026-10-29T09:01:00+00:00"},       # back again
              {"event_type": "step_entered", "step": "describe_complaint", "at": "2026-10-29T10:01:00+00:00"}]   # another hour
    got = sessions_svc.step_durations(events, None)
    assert got["review_details"] == 1200.0 and got["describe_complaint"] == 60.0                                  # 600 + 600


def test_dashboard_step_card_has_mean_median_and_the_cap(client):
    register(client, headers=EMP, participant="PA")
    register(client, headers=B1, participant="PB")
    s = client.get("/api/analytics/summary", headers=ADMIN).json()
    row = s["step_seconds"]["find_customer"]
    assert set(row) == {"mean", "median", "n"} and row["n"] == 2
    assert s["step_cap_seconds"] == 600


def test_the_registration_clock_starts_when_the_form_opens(client):
    """The session is created when the customer is chosen; the client says how long the form had been open."""
    from datetime import datetime
    seconds_ago = lambda started: (datetime.fromisoformat(db_now()) - datetime.fromisoformat(started)).total_seconds()
    s = client.post("/api/sessions", headers=EMP, json={"opened_seconds_ago": 45}).json()
    assert 45 <= seconds_ago(s["started"]) <= 60                                                  # the session began when the form opened
    row = next(i for i in client.get("/api/analytics/sessions", headers=ADMIN).json()["items"] if i["id"] == s["session_id"])
    assert row["started"] == s["started"]
    long = client.post("/api/sessions", headers=EMP, json={"opened_seconds_ago": 5000}).json()    # an idle form: capped at 10 minutes
    assert 600 <= seconds_ago(long["started"]) <= 620
    assert client.post("/api/sessions", headers=EMP, json={"opened_seconds_ago": -1}).status_code == 422
    assert client.post("/api/sessions", headers=EMP, json={}).status_code == 201                   # old clients still work


def db_now():
    from backend import db
    return db.now()


def test_time_to_first_field_and_first_own_entry(client):
    sid = client.post("/api/sessions", headers=EMP, json={"opened_seconds_ago": 30}).json()["session_id"]
    ev = lambda **b: client.post(f"/api/sessions/{sid}/events", headers=EMP, json={"type": "field", **b})
    ev(field="customer_id", origin="prefilled")          # the lookup fills the first field
    ev(field="channel", origin="blank")                  # a blank field is not "filled"
    ev(field="complaint_type", origin="manual", changed=True)   # the employee's own entry
    row = next(i for i in client.get("/api/analytics/sessions", headers=ADMIN).json()["items"] if i["id"] == sid)
    assert 30 <= row["first_field_seconds"] <= 40 and row["first_field_seconds"] <= row["first_entry_seconds"] <= 45
    s = client.get("/api/analytics/summary", headers=ADMIN).json()
    assert s["first_field_seconds"]["n"] == 1 and s["first_entry_seconds"]["n"] == 1 and s["first_field_seconds"]["median"] >= 30
    table = rows(client.get("/api/export/sessions.csv", headers=ADMIN))
    head = table[0]
    assert head[8:11] == ["root_cause", "repeat", "failure"] and head[11:13] == ["first_field_s", "first_entry_s"]
    mine = next(r for r in table[1:] if r[0] == sid)
    assert float(mine[11]) >= 30 and float(mine[12]) >= float(mine[11])


def test_sessions_without_any_field_have_no_first_field_time(client):
    sid = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    row = next(i for i in client.get("/api/analytics/sessions", headers=ADMIN).json()["items"] if i["id"] == sid)
    assert row["first_field_seconds"] is None and row["first_entry_seconds"] is None
    assert client.get("/api/analytics/summary", headers=ADMIN).json()["first_field_seconds"] == {"mean": None, "median": None, "n": 0}
