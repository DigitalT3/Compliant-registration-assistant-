"""Repeat-rule sign-off by its owner, and the go/no-go readout for the business owner."""
import copy

from backend import db
from backend.services import rule_signoff
from tests.conftest import ADMIN, EMP
from tests.integration.test_step4_usertest import LEAD
from tests.integration.test_team_scope import signed_in

RULE = "/api/config/repeat-rule"
NEW_RULE = {"enabled": True, "lookback_days": 30, "match_keys": ["customer_id"], "cause_mode": "level1",
            "eligible_statuses": ["open", "closed"], "missing_values": "no_match"}


def test_the_rule_starts_as_a_draft_and_only_its_owner_signs_it_off(client):
    assert client.get(RULE).json()["signoff"]["state"] == "draft"
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    for headers in (EMP, LEAD):                                                           # the administrator can do everything the other roles can
        assert client.post(RULE + "/signoff", headers=headers, json={"decision": "sign_off"}).status_code == 403
    assert client.post(RULE + "/signoff", headers=juul, json={"decision": "changes"}).json()["error"]["code"] == "comment_required"
    done = client.post(RULE + "/signoff", headers=juul, json={"decision": "sign_off"}).json()
    assert done["state"] == "signed_off" and done["signed_by"] == ["Test Juul"] and done["signed_at"]
    assert client.get("/api/config").json()["rule_signoff"]["state"] == "signed_off"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit WHERE action='repeat_rule_signed_off'").fetchone()[0] == 1


def test_the_rule_owner_can_edit_and_an_edit_voids_the_sign_off(client):
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    client.post(RULE + "/signoff", headers=juul, json={"decision": "sign_off"})
    assert client.put(RULE, headers=EMP, json=NEW_RULE).status_code == 403
    assert client.put(RULE, headers=juul, json=NEW_RULE).status_code == 200              # Juul edits without being an administrator
    after = client.get(RULE).json()["signoff"]
    assert after["state"] == "draft" and after["signed"] == 0
    assert len(after["reviews"]) == 1 and not after["reviews"][0]["current"]            # the old sign-off stays as history
    assert client.post(RULE + "/signoff", headers=juul, json={"decision": "sign_off"}).json()["state"] == "signed_off"


def test_the_rule_owner_sees_the_disputes_but_not_the_other_settings(client):
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    assert client.get("/api/repeat-disputes", headers=juul).status_code == 200
    assert client.put("/api/config/defaults", headers=juul, json={"defaults": {}}).status_code == 403
    assert client.get("/api/readout", headers=juul).status_code == 403


def test_a_change_to_the_parameters_changes_the_fingerprint():
    cfg = rule_signoff.get_config()
    other = copy.deepcopy(cfg)
    other["repeat_rule"]["lookback_days"] += 1
    assert rule_signoff.content_hash(cfg) != rule_signoff.content_hash(other)
    other = copy.deepcopy(cfg)
    other["repeat_rule"]["version"] = "something-else"                                    # the label alone is not a change of the rule
    assert rule_signoff.content_hash(cfg) == rule_signoff.content_hash(other)


def test_the_readout_shows_evidence_and_open_conditions_to_the_right_roles(client):
    glenn = signed_in(client, "glenn@example.nl", None, role="business_owner")
    for headers in (EMP, LEAD, {"X-Demo-User": "demo.viewer"}):
        assert client.get("/api/readout", headers=headers).status_code == 403
    for headers in (glenn, ADMIN, {"X-Demo-User": "demo.evaluator"}):
        assert client.get("/api/readout", headers=headers).status_code == 200
    ev = client.get("/api/readout", headers=glenn).json()
    conds = {c["id"]: c for c in ev["conditions"]}
    assert not conds["cause_list"]["ok"] and not conds["repeat_rule"]["ok"] and ev["decisions"] == []
    assert set(conds) == {"cause_list", "repeat_rule", "sessions", "labels", "interviews", "baseline"}
    csv = client.get("/api/export/readout.csv", headers=glenn)
    assert csv.status_code == 200 and "condition,cause_list" in csv.text


def test_only_the_business_owner_records_the_decision_with_a_reason(client):
    glenn = signed_in(client, "glenn@example.nl", None, role="business_owner")
    body = {"decision": "conditional", "comment": "Go once the cause list is agreed"}
    for headers in ({"X-Demo-User": "demo.evaluator"}, EMP):
        assert client.post("/api/readout/decision", headers=headers, json=body).status_code == 403
    assert client.post("/api/readout/decision", headers=glenn, json={"decision": "go", "comment": "  "}).status_code == 422
    assert client.post("/api/readout/decision", headers=glenn, json={"decision": "maybe", "comment": "x"}).status_code == 422
    ev = client.post("/api/readout/decision", headers=glenn, json=body).json()
    d = ev["decisions"][0]
    assert (d["decision"], d["name"], d["comment"]) == ("conditional", "Test Glenn", body["comment"])
    assert {c["id"] for c in d["conditions"]} >= {"cause_list", "repeat_rule"}               # the evidence it rested on is kept
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit WHERE action='go_no_go_decision'").fetchone()[0] == 1


def test_an_administrator_may_sign_but_only_the_rule_owner_signs_it_off(client):
    done = client.post(RULE + "/signoff", headers=ADMIN, json={"decision": "sign_off"}).json()
    assert done["state"] == "draft" and done["reviews"][0]["counts"] is False
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    ok = client.post(RULE + "/signoff", headers=juul, json={"decision": "sign_off"}).json()
    assert ok["state"] == "signed_off" and ok["signed_by"] == ["Test Juul"]
