"""Team lead view: how each person registers (volume, time and its spread, how much of the assistant is kept)."""
import copy
import csv
import io

from backend import db
from backend.services import metrics
from tests.conftest import ADMIN
from tests.integration.test_step4_usertest import LEAD, register

A1 = {"X-Demo-User": "demo.emp.a1"}      # group_a
A2 = {"X-Demo-User": "demo.emp.a2"}      # group_a
B1 = {"X-Demo-User": "demo.emp.b1"}      # group_b
KEPT = {"summary": "suggested", "root_cause": "suggested", "complaint_type": "suggested", "channel": "default", "container": "prefilled"}
CHANGED = {"summary": "edited", "root_cause": "edited", "complaint_type": "manual", "channel": "default", "container": "blank"}


def rows(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def setup_team(client):
    for _ in range(3):
        register(client, headers=A1, field_provenance=KEPT)        # a1: three registrations, assistant kept
    register(client, headers=A2, field_provenance=KEPT)            # a2: one registration only
    for _ in range(3):
        register(client, headers=B1, field_provenance=CHANGED)     # b1 (other team): three, everything changed


def by_name(data):
    return {e["employee"]: e for e in data["employees"]}


def test_per_employee_numbers_and_the_small_sample_guard(client):
    setup_team(client)
    data = client.get("/api/analytics/employees", headers=ADMIN).json()
    e = by_name(data)
    a1, a2, b1 = e["Demo Employee A1"], e["Demo Employee A2"], e["Demo Employee B1"]
    assert (a1["saved"], a1["team"]) == (3, "group_a") and a1["enough_data"] is True
    assert a1["summary_accepted"] == {"value": 1.0, "n": 3} and a1["cause_accepted"] == {"value": 1.0, "n": 3}
    assert b1["summary_accepted"] == {"value": 0.0, "n": 3} and b1["cause_accepted"] == {"value": 0.0, "n": 3}
    assert a1["min_seconds"] <= a1["median_seconds"] <= a1["max_seconds"]                   # the spread is reported
    assert a2["saved"] == 1 and a2["enough_data"] is False                                    # one registration is no basis to judge
    assert a2["summary_accepted"]["value"] is None and a2["median_seconds"] is None and a2["prefill_rate"]["value"] is None
    assert data["team"]["saved"] == 7 and data["min_n"] == 3
    assert [x["employee"] for x in data["employees"]][:2] in (["Demo Employee A1", "Demo Employee B1"], ["Demo Employee B1", "Demo Employee A1"])


def test_a_team_lead_sees_only_the_people_of_their_team(client):
    setup_team(client)
    data = client.get("/api/analytics/employees", headers=LEAD, params={"group": "group_b"}).json()   # a team in the request is ignored
    assert set(by_name(data)) == {"Demo Employee A1", "Demo Employee A2"}
    assert data["scope"] == {"team": "group_a"} and data["team"]["saved"] == 4
    assert len(set(by_name(client.get("/api/analytics/employees", headers=ADMIN).json()))) == 3     # admins see every team
    with db.connect() as conn:
        conn.execute("INSERT INTO users(id,name,role,user_group,function) VALUES('demo.lead.noteam','No Team','lead','leads',NULL)")
        conn.commit()
    r = client.get("/api/analytics/employees", headers={"X-Demo-User": "demo.lead.noteam"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "team_required"


def test_names_can_be_hidden(client, monkeypatch):
    setup_team(client)
    cfg = copy.deepcopy(metrics.get_config())
    cfg["report"]["show_employee_names"] = False
    monkeypatch.setattr(metrics, "get_config", lambda: cfg)
    data = client.get("/api/analytics/employees", headers=ADMIN).json()
    assert data["names_shown"] is False
    assert {e["employee"] for e in data["employees"]} == {"Employee 1", "Employee 2", "Employee 3"}
    assert all("id" not in e for e in data["employees"])                                         # nothing that identifies a person
    assert "Demo Employee" not in client.get("/api/export/employees.csv", headers=ADMIN).text


def test_repeat_decisions_are_counted_per_person(client):
    cid, _ = register(client, headers=A1, field_provenance=KEPT)
    r = client.post("/api/repeat-disputes", headers=A1, json={"complaint_id": cid, "prior_complaint_id": "COM-SEED-1",
                                                              "decision": "reject", "reason": "Different container"})
    assert r.status_code == 201
    a1 = by_name(client.get("/api/analytics/employees", headers=ADMIN).json())["Demo Employee A1"]
    assert (a1["repeat_decisions"], a1["repeat_rejected"]) == (1, 1)


def test_the_export_has_a_team_row_and_follows_the_same_limits(client):
    setup_team(client)
    table = rows(client.get("/api/export/employees.csv", headers=LEAD, params={"group": "group_b"}))
    head = table[0]
    assert head[:5] == ["employee", "team", "started", "saved", "abandoned"] and "summary_accepted" in head and "enough_data" in head
    assert [r[0] for r in table[1:]][0] == "Team"
    names = {r[0] for r in table[2:]}
    assert names == {"Demo Employee A1", "Demo Employee A2"}                                       # no one from the other team
    a2 = next(r for r in table if r[0] == "Demo Employee A2")
    assert a2[head.index("summary_accepted")] == "" and a2[head.index("enough_data")] == "0"       # too few: left empty
    a1 = next(r for r in table if r[0] == "Demo Employee A1")
    assert a1[head.index("summary_accepted")] == "1.0"
    assert client.get("/api/export/employees.csv", headers=A1).status_code == 403                  # employees have no analytics
    assert client.get("/api/analytics/employees", headers=A1).status_code == 403


def test_nothing_recorded_gives_an_empty_view(client):
    data = client.get("/api/analytics/employees", headers=ADMIN).json()
    assert data["employees"] == [] and data["team"] is None


def test_a_real_lead_sees_the_real_people_of_their_team_without_any_demo_header(client):
    """Real accounts, temporary passwords and tokens only: the per-employee view works outside demo mode."""
    from tests.integration.test_team_scope import PROV, signed_in
    sanne = signed_in(client, "sanne.sales@example.nl", "sales")
    sven = signed_in(client, "sven.sales@example.nl", "sales")
    karel = signed_in(client, "karel.service@example.nl", "customer_service")
    lead = signed_in(client, "lotte.lead@example.nl", "sales", role="lead")
    for _ in range(3):
        register(client, headers=sanne, field_provenance={**PROV, "summary": "suggested", "root_cause": "suggested"})
    register(client, headers=sven, field_provenance=PROV)
    for _ in range(3):
        register(client, headers=karel, field_provenance=PROV)

    data = client.get("/api/analytics/employees", headers=lead, params={"group": "customer_service"}).json()
    got = by_name(data)
    assert set(got) == {"Test Sanne.Sales", "Test Sven.Sales"}                                  # the lead's own team, real accounts
    assert data["scope"] == {"team": "sales"} and data["team"]["saved"] == 4
    assert got["Test Sanne.Sales"]["saved"] == 3 and got["Test Sanne.Sales"]["team"] == "sales"
    assert got["Test Sanne.Sales"]["summary_accepted"] == {"value": 1.0, "n": 3}
    assert got["Test Sven.Sales"]["summary_accepted"]["value"] is None                          # one registration: hidden
    table = rows(client.get("/api/export/employees.csv", headers=lead))
    assert {r[0] for r in table[2:]} == {"Test Sanne.Sales", "Test Sven.Sales"}
    all_teams = client.get("/api/analytics/employees", headers=ADMIN).json()
    assert {"Test Karel.Service"} <= set(by_name(all_teams))                                    # the admin sees every team
    assert client.get("/api/analytics/employees", headers=karel).status_code == 403             # employees cannot open it
