"""Audit Trail: an administrator sees every saved record and how it was made."""
import json

from backend import db
from backend.services import field_mapping
from tests.conftest import ADMIN, EMP
from tests.integration.test_team_scope import signed_in

GOV = {"X-Demo-User": "demo.governance"}


def _register(client, **extra):
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    body = {"customer_id": "C001", "site_id": "C001-S1", "channel": "phone", "complaint_type": "service", "root_cause": "missed",
            "description": "Container missed again.", "session_id": sid,
            "field_provenance": {"customer_id": "prefilled", "channel": "default", "description": "manual", "root_cause": "suggested"},
            "repeat_decisions": [{"prior_complaint_id": "COM-SEED-1", "decision": "reject", "reason": "Different container"}], **extra}
    r = client.post("/api/complaints", headers=EMP, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_only_administrators_and_governance_can_see_the_audit_trail(client):
    cid = _register(client)
    for headers in (ADMIN, GOV):
        assert client.get("/api/audit/records", headers=headers).status_code == 200
        assert client.get(f"/api/audit/records/{cid}", headers=headers).status_code == 200
    lead = signed_in(client, "lotte@example.nl", "sales", role="lead")
    for headers in (EMP, {"X-Demo-User": "demo.viewer"}, {"X-Demo-User": "demo.evaluator"}, lead):
        assert client.get("/api/audit/records", headers=headers).status_code == 403
        assert client.get(f"/api/audit/records/{cid}", headers=headers).status_code == 403
        assert client.get("/api/export/records.csv", headers=headers).status_code == 403
    assert client.get("/api/audit/records").status_code == 401


def test_the_list_shows_every_saved_record_registrations_first(client):
    cid = _register(client)
    with db.connect() as conn:
        everything = conn.execute("SELECT count(*) FROM complaints").fetchone()[0]
    out = client.get("/api/audit/records", headers=ADMIN, params={"page_size": 100}).json()
    assert out["total"] == everything and everything > 40
    first = out["items"][0]
    assert first["id"] == cid and first["is_seed"] == 0 and first["customer_name"] and first["site_name"] and first["registered_by"]
    flags = [i["is_seed"] for i in out["items"]]
    assert flags == sorted(flags)                                                          # the PoC's own records, then the synthetic history
    assert client.get("/api/audit/records", headers=ADMIN, params={"include_seed": "false"}).json()["total"] == 1


def test_the_list_can_be_searched_by_id_customer_name_or_number(client):
    cid = _register(client)
    by = lambda q: [i["id"] for i in client.get("/api/audit/records", headers=ADMIN, params={"q": q, "page_size": 100}).json()["items"]]
    assert cid in by(cid) and cid in by("delta works") and cid in by("100001") and by("zzz-nothing") == []


def test_a_record_opens_in_the_target_structure_with_how_it_was_made(client):
    cid = _register(client)
    d = client.get(f"/api/audit/records/{cid}", headers=ADMIN).json()
    assert list(d["record"]) == [f["target_field"] for f in field_mapping.load()["fields"]] and d["missing_required"] == []
    assert d["record"]["PROVISIONAL_ComplaintId"] == cid and d["record"]["PROVISIONAL_Description"] == "Container missed again."
    origins = {o["field"]: o["origin"] for o in d["origins"]}
    assert origins["customer_id"] == "prefilled" and origins["channel"] == "default" and origins["description"] == "manual" and len(origins) == 15
    actions = [e["action"] for e in d["events"]]
    assert {"complaint_saved", "repeat_rule_evaluated", "repeat_match_disputed", "session_completed"} <= set(actions)
    saved = next(e for e in d["events"] if e["action"] == "complaint_saved")
    assert saved["actor_name"] == "Demo Employee A1" and saved["at"]
    assert d["repeat_checks"][0]["is_repeat"] == 1 and d["repeat_disputes"][0]["reason"] == "Different container"
    assert client.get("/api/audit/records/NOPE", headers=ADMIN).status_code == 404


def test_events_of_another_record_are_not_mixed_in(client):
    a, b = _register(client), _register(client)
    ev = lambda cid: client.get(f"/api/audit/records/{cid}", headers=ADMIN).json()["events"]
    assert all(cid not in json.dumps(ev(a)) for cid in (b,)) and ev(a) != ev(b)
    assert sum(e["action"] == "complaint_saved" for e in ev(a)) == 1


def test_the_export_is_the_whole_store_in_the_target_field_names_and_is_logged(client):
    _register(client)
    r = client.get("/api/export/records.csv", headers=ADMIN, params={"include_seed": "true"})
    lines = r.text.splitlines()
    with db.connect() as conn:
        everything = conn.execute("SELECT count(*) FROM complaints").fetchone()[0]
        logged = conn.execute("SELECT count(*) FROM audit WHERE action='records_exported'").fetchone()[0]
    assert lines[0].split(",") == [f["target_field"] for f in field_mapping.load()["fields"]]
    assert len(lines) - 1 >= everything and logged == 1                                  # (multi-line texts can add lines)
    only_new = client.get("/api/export/records.csv", headers=ADMIN).text.splitlines()
    assert len(only_new) == 2                                                             # header + the one registration


def test_a_description_that_looks_like_a_formula_is_neutralised_in_the_export(client):
    _register(client, description="=HYPERLINK(\"http://example.com\")")
    assert "'=HYPERLINK" in client.get("/api/export/records.csv", headers=ADMIN).text


def test_registrations_that_were_started_but_not_saved_are_listed_with_their_log(client):
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant", "participant_id": "P-9", "scenario": "T1"}).json()["session_id"]
    card = client.get("/api/customers/search", params={"q": "100009"}, headers=EMP).json()["candidates"][0]
    client.post("/api/prefill", headers=EMP, json={"customer_id": card["customer_id"], "origin": "search", "guess_site": True, "session_id": sid})
    for a, b in (("find_customer", "review_details"), ("review_details", "describe_complaint")):
        client.post(f"/api/sessions/{sid}/events", headers=EMP, json={"type": "step_completed", "step": a})
        client.post(f"/api/sessions/{sid}/events", headers=EMP, json={"type": "step_entered", "step": b})
    client.post(f"/api/sessions/{sid}/complete", headers=EMP, json={"outcome": "abandoned"})
    out = client.get("/api/audit/unsaved", headers=ADMIN).json()
    row = next(r for r in out["items"] if r["id"] == sid)
    assert (row["status"], row["mode"], row["participant_id"], row["scenario"], row["last_step"]) == ("abandoned", "assistant", "P-9", "T1", "describe_complaint")
    assert [s["step"] for s in row["steps"]] == ["find_customer", "review_details", "describe_complaint", "classify", "repeat_save"]
    assert row["fields_logged"] >= 9 and row["actor_name"] == "Demo Employee A1"
    assert client.get("/api/audit/unsaved", headers=EMP).status_code == 403
    saved = _register(client)                                                              # a saved registration is not listed there
    assert saved and all(r["id"] != client.get(f"/api/audit/records/{saved}", headers=ADMIN).json()["log"].get("session") for r in client.get("/api/audit/unsaved", headers=ADMIN).json()["items"])
