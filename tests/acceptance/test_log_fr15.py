"""FR-15: the log per registration (time per step, fields prefilled, suggestions shown, accepted or changed) is complete for every test registration."""
from backend import db
from backend.services import sessions as sessions_svc
from tests.conftest import ADMIN, EMP

TEXT = "The container at our depot was not emptied on Tuesday, it was missed again."


def _registration(client, mode="assistant", edit=None, skip_steps=(), cause_index=0):
    """One registration the way the screen makes it: steps, prefill, suggestions, edits, save."""
    sid = client.post("/api/sessions", headers=EMP, json={"mode": mode}).json()["session_id"]
    ev = lambda **b: client.post(f"/api/sessions/{sid}/events", headers=EMP, json=b)
    card = client.get("/api/customers/search", params={"q": "100009"}, headers=EMP).json()["candidates"][0]
    client.post("/api/prefill", headers=EMP, json={"customer_id": card["customer_id"], "origin": "search", "guess_site": True, "session_id": sid})
    steps = [s for s in sessions_svc.STEPS if s not in skip_steps]
    for a, b in zip(steps, steps[1:]):
        ev(type="step_completed", step=a)
        ev(type="step_entered", step=b)
    shown, summary = [], None
    if mode == "assistant":
        shown = client.post("/api/complaints/classify", headers=EMP, json={"text": TEXT, "session_id": sid}).json()["result"]
        summary = client.post("/api/complaints/summarise", headers=EMP, json={"text": TEXT, "site_id": "C009-S1", "complaint_type": "service", "session_id": sid}).json()["result"]
        if edit:
            summary = {**summary, **edit}                                                    # the employee changes the summary
    if edit:
        ev(type="field", field="channel", origin="edited", changed=True)
    cause = shown["candidates"][cause_index]["root_cause_id"] if shown else "missed"
    prov = {k: "prefilled" for k in ("customer_id", "site_id", "contract_id", "order_id", "container", "registration_date", "registering_user")}
    prov.update(channel="edited" if edit else "default", priority="default", status="default", owner_team="default", complaint_type="suggested" if shown else "manual",
                root_cause="suggested" if cause_index == 0 and shown else "manual", description="manual", summary="edited" if edit else "suggested" if shown else "blank")
    r = client.post("/api/complaints", headers=EMP, json={"customer_id": card["customer_id"], "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
                    "root_cause": cause, "description": TEXT, "session_id": sid, "summary": summary, "field_provenance": prov})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _log(client, cid):
    return client.get(f"/api/audit/records/{cid}", headers=ADMIN).json()["log"]


def test_a_complete_assistant_registration_has_a_complete_log(client):
    log = _log(client, _registration(client))
    assert log["complete"] is True and log["missing"] == [] and log["mode"] == "assistant" and log["status"] == "saved"
    assert [s["step"] for s in log["steps"]] == sessions_svc.STEPS and all(s["visits"] >= 1 for s in log["steps"])      # time per step: all five steps
    assert log["total_seconds"] >= 0 and log["started"] and log["ended"]
    assert log["prefilled_at_start"]["prefilled"] >= 7 and log["prefilled_at_start"]["default"] >= 3                    # fields prefilled before the employee touched them
    assert sum(log["fields_at_save"].values()) == 15                                                                    # the origin of every tracked field at save


def test_the_suggestions_shown_are_kept_with_their_reasons(client):
    s = _log(client, _registration(client))["suggestions"]
    assert s["complaint_type"] == "service"
    assert 1 <= len(s["causes"]) <= 3 and all(c["root_cause_id"] and c["reason"] and "confidence" in c for c in s["causes"])
    assert {c["operation"] for c in s["ai_calls"]} >= {"classify", "summarise"} and all(c["status"] == "ok" for c in s["ai_calls"])
    assert s["summary_suggested"]["what"]                                                                              # what the assistant wrote, not only what was saved


def test_accepted_or_changed_is_recorded_for_the_cause_and_the_summary(client):
    kept = _log(client, _registration(client))["suggestions"]
    assert kept["cause_result"] == "kept_first" and kept["in_top3"] == 1 and kept["summary_result"] == "kept" and kept["summary_changed_fields"] == []
    edited = _log(client, _registration(client, edit={"impact": "Overflowing bin, customer upset"}))
    assert edited["suggestions"]["summary_result"] == "changed" and edited["suggestions"]["summary_changed_fields"] == ["impact"]
    assert any(e["field"] == "channel" and e["origin"] == "edited" for e in edited["edits"])                          # edits during the registration are logged as changes
    assert edited["fields_at_save"].get("edited", 0) >= 1


def test_a_cause_outside_the_suggestions_is_recorded_as_such(client):
    sid_cid = _registration(client, cause_index=0)
    log = _log(client, sid_cid)
    assert log["suggestions"]["cause_result"] == "kept_first"
    with db.connect() as conn:                                                           # same registration, but the saved cause was not among the suggestions
        conn.execute("UPDATE ai_events SET selected='weighing', in_top3=0 WHERE operation='classification_outcome' AND session_id=(SELECT session_id FROM complaints WHERE id=?)", (sid_cid,))
        conn.commit()
    assert _log(client, sid_cid)["suggestions"]["cause_result"] == "chose_outside"


def test_a_plain_form_registration_is_complete_without_suggestions(client):
    log = _log(client, _registration(client, mode="plain"))
    assert log["complete"] is True and log["mode"] == "plain" and log["suggestions"]["causes"] == [] and log["suggestions"]["ai_calls"] == []


def test_a_registration_with_a_hole_in_its_log_is_reported_as_incomplete(client):
    log = _log(client, _registration(client, skip_steps=("describe_complaint",)))
    assert log["complete"] is False and any(m.startswith("step_not") and "describe_complaint" in m for m in log["missing"])
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]       # saved without any logged work
    cid = client.post("/api/complaints", headers=EMP, json={"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
                      "root_cause": "missed", "description": "x y z", "session_id": sid}).json()["id"]
    bad = _log(client, cid)
    assert bad["complete"] is False and {"suggestions_not_logged", "prefill_not_logged"} <= set(bad["missing"])
    nosess = client.post("/api/complaints", headers=EMP, json={"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service", "root_cause": "missed", "description": "x y z"}).json()["id"]
    assert _log(client, nosess)["missing"] == ["session"]


def test_the_list_flags_each_record_and_synthetic_history_is_not_applicable(client):
    good, plain = _registration(client), _registration(client, mode="plain")
    bad = client.post("/api/complaints", headers=EMP, json={"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service", "root_cause": "missed", "description": "x y z"}).json()["id"]
    items = {i["id"]: i["log"] for i in client.get("/api/audit/records", headers=ADMIN, params={"page_size": 100}).json()["items"]}
    assert items[good] == "complete" and items[plain] == "complete" and items[bad] == "incomplete"
    assert items["COM-SEED-1"] == "n/a"
    assert _log(client, "COM-SEED-1") == {"applicable": False, "reason": "synthetic_history"}


def test_moving_on_to_the_next_step_counts_as_completing_a_step(client):
    """The first step is closed by entering the second (older registrations never logged its completion separately)."""
    cid = _registration(client)
    with db.connect() as conn:
        sid = conn.execute("SELECT session_id FROM complaints WHERE id=?", (cid,)).fetchone()[0]
        conn.execute("DELETE FROM step_events WHERE session_id=? AND step='find_customer' AND event_type='step_completed'", (sid,))
        conn.commit()
    assert _log(client, cid)["complete"] is True
    with db.connect() as conn:                                                   # but the last step must be completed by the save itself
        conn.execute("DELETE FROM step_events WHERE session_id=? AND step='repeat_save' AND event_type='step_completed'", (sid,))
        conn.commit()
    assert _log(client, cid)["missing"] == ["step_not_completed:repeat_save"]


def test_a_container_filled_from_the_order_is_not_counted_as_the_employee_changing_the_summary(client):
    cid = _registration(client)
    with db.connect() as conn:
        row = conn.execute("SELECT id, summary_json FROM complaints WHERE id=?", (cid,)).fetchone()
        import json
        saved = json.loads(row["summary_json"])
        saved.setdefault("extras", {})["container_no"] = "BOX-009-1"
        saved["context_extras"] = ["container_no"]
        conn.execute("UPDATE complaints SET summary_json=? WHERE id=?", (json.dumps(saved), cid))
        conn.commit()
    assert _log(client, cid)["suggestions"]["summary_result"] == "kept"


def test_rating_samples_are_not_test_registrations(client):
    cid = client.post("/api/complaints", headers=EMP, json={"customer_id": "C005", "site_id": "C005-S1", "channel": "phone", "complaint_type": "service",
                      "root_cause": "missed", "description": "Sample text.", "scenario": "rating-sample-S01"}).json()["id"]
    assert _log(client, cid) == {"applicable": False, "reason": "rating_sample"}
    assert {i["id"]: i["log"] for i in client.get("/api/audit/records", headers=ADMIN).json()["items"]}[cid] == "n/a"
