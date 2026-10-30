"""FR-08: a structured summary (what, where, when, impact + the type's own fields), editable, rated usable by the process owners."""
import json
from pathlib import Path

from tests.conftest import ADMIN, EMP
from tests.integration.test_team_scope import signed_in

CASES = json.loads((Path(__file__).parent / "summary_cases.json").read_text(encoding="utf-8"))["cases"]
EXTRAS = {"service": {"expected_vs_actual_service_date", "container_no"}, "billing": {"invoice_no", "amount_disputed"}, "conduct": {"who_or_vehicle_if_known"}}


def _analyze(client, case):
    return client.post("/api/complaints/analyze", headers=EMP, json={"text": case["text"], "complaint_type": case["type"], "container": case.get("container")}).json()


def test_every_type_gets_the_four_fields_and_its_own_template_fields(client):
    for case in CASES:
        out = _analyze(client, case)
        assert out["ai_status"] == "ok", case["id"]
        s = out["result"]["summary"]
        assert {"what", "where", "when", "impact", "language", "extras"} <= set(s), case["id"]
        assert set(s["extras"]) <= EXTRAS[case["type"]], (case["id"], s["extras"])


def test_the_summary_is_saved_as_edited_by_the_employee(client):
    case = CASES[0]
    s = _analyze(client, case)["result"]["summary"]
    s["impact"] = "Edited by the employee"                                                   # the summary is editable before saving
    saved = client.post("/api/complaints", headers=EMP, json={
        "customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": case["type"], "root_cause": "missed",
        "description": case["text"], "language": case["language"], "summary": s, "summary_meta": {"mock": True}}).json()
    rec = client.get(f"/api/complaints/{saved['id']}", headers=EMP).json()
    assert rec["summary_json"]["impact"] == "Edited by the employee" and rec["original_text"] == case["text"]


def _ten_registered(client):
    """Ten saved complaints, each with its own session (the dashboard only counts sessions)."""
    ids = []
    for case in CASES:
        sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
        s = _analyze(client, case)["result"]["summary"]
        ids.append(client.post("/api/complaints", headers=EMP, json={
            "customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": case["type"], "root_cause": "missed",
            "description": case["text"], "language": case["language"], "summary": s, "session_id": sid}).json()["id"])
    return ids


def _target(client):
    t = client.get("/api/analytics/summary", headers=ADMIN).json()["targets"]
    return next(x for x in t if x["id"] == "summary_usable")


def test_eight_of_ten_rated_usable_meets_the_target_and_seven_does_not(client):
    ids = _ten_registered(client)
    owner = signed_in(client, "olga@example.nl", None, role="evaluator")
    for i, cid in enumerate(ids):
        assert client.post("/api/evaluations", headers=owner, json={"complaint_id": cid, "usable": i >= 2}).status_code == 201
    t = _target(client)
    assert (t["value"], t["n"], t["status"]) == (0.8, 10, "met")
    client.post("/api/evaluations", headers=owner, json={"complaint_id": ids[2], "usable": False})     # she changes her mind on one
    t = _target(client)
    assert (t["value"], t["n"], t["status"]) == (0.7, 10, "not_met")                                   # her latest rating counts, not both


def test_several_owners_each_count_once_per_complaint(client):
    ids = _ten_registered(client)[:4]
    owners = [signed_in(client, f"{n}@example.nl", None, role="evaluator") for n in ("kwafie", "naomi", "maikel")]
    for h in owners:
        for cid in ids:
            client.post("/api/evaluations", headers=h, json={"complaint_id": cid, "usable": True})
            client.post("/api/evaluations", headers=h, json={"complaint_id": cid, "usable": True})       # a double click is not a second vote
    assert client.get("/api/evaluations", headers=owners[0]).json()["usable"] == {"value": 1.0, "n": 12}


def test_the_rating_sample_shows_the_whole_summary_and_skips_what_the_rater_did(client):
    ids = _ten_registered(client)
    owner = signed_in(client, "olga@example.nl", None, role="evaluator")
    first = client.get("/api/evaluations/sample?limit=50", headers=owner).json()["items"]
    assert len(first) == 10 and {"what", "where", "when", "impact", "extras"} <= set(first[0]["summary"])
    assert "root_cause" not in first[0] and "complaint_type" not in first[0]                              # blind
    client.post("/api/evaluations", headers=owner, json={"complaint_id": ids[0], "usable": True})            # rated without choosing a cause
    left = [i["id"] for i in client.get("/api/evaluations/sample?limit=50", headers=owner).json()["items"]]
    assert ids[0] not in left and len(left) == 9
    assert client.get("/api/evaluations/sample", headers=EMP).status_code == 403
