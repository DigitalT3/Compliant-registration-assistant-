"""FR-12: the repeat rule before saving, 100% of seeded repeats flagged, no flag on seeded non-repeats. FR-13: confirm or dispute a link, logged for the rule owner."""
import json
from pathlib import Path

import pytest

from backend import db
from scripts.seed_rating_sample import PLACES
from tests.conftest import ADMIN, EMP
from tests.integration.test_team_scope import signed_in

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = [s for s in json.loads((ROOT / "backend/seed_data/scenarios.json").read_text(encoding="utf-8"))["scenarios"] if s.get("repeat_candidate")]
T10 = next(s for s in SCENARIOS if s["id"] == "T10")["repeat_candidate"]
T14 = next(s for s in SCENARIOS if s["id"] == "T14")["repeat_candidate"]


def _check(client, cand):
    return client.post("/api/complaints/check-repeat", headers=EMP, json={k: cand[k] for k in ("customer_id", "site_id", "root_cause")}).json()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_every_seeded_scenario_gets_the_expected_answer(client, scenario):
    out, want = _check(client, scenario["repeat_candidate"]), scenario["expected"]
    assert out["is_repeat"] is want["repeat"] and [m["id"] for m in out["matches"]] == want["matches"]
    for m in out["matches"]:                                                            # the linked earlier complaints are shown with their evidence
        assert m["id"] and (m.get("date") or m.get("created")) and m["status"] and m.get("cause") or m.get("root_cause")


def test_all_seeded_repeats_flagged_and_no_seeded_non_repeat_flagged(client):
    flagged = [bool(_check(client, s["repeat_candidate"])["is_repeat"]) for s in SCENARIOS]
    expected = [s["expected"]["repeat"] for s in SCENARIOS]
    assert (sum(f and e for f, e in zip(flagged, expected)), sum(expected)) == (4, 4)               # 100% of the seeded repeats
    assert not any(f and not e for f, e in zip(flagged, expected))                                   # none of the seeded non-repeats


def test_the_rating_sample_never_lands_on_a_scenario_customer():
    scenario_customers = {s["repeat_candidate"]["customer_id"] for s in SCENARIOS}
    assert not scenario_customers & {customer for customer, _ in PLACES}, "sample complaints there would change the repeat answers"


def test_the_check_runs_before_saving_and_a_stale_check_is_refused(client):
    first = _check(client, T10)
    body = {**T10, "channel": "phone", "complaint_type": "service", "description": "Again.", "repeat_input_hash": first["input_hash"]}
    assert client.post("/api/complaints", headers=EMP, json=body).status_code == 201
    assert client.post("/api/complaints", headers=EMP, json={**body, "root_cause": "late"}).json()["error"]["code"] == "stale_repeat_check"


def _save(client, headers=EMP, cand=None, **extra):
    cand = cand or T14
    return client.post("/api/complaints", headers=headers, json={**cand, "channel": "phone", "complaint_type": "service", "description": "Again.", **extra})


def _count():
    with db.connect() as conn:
        return conn.execute("SELECT count(*) FROM complaints").fetchone()[0], conn.execute("SELECT count(*) FROM repeat_disputes").fetchone()[0]


def test_decisions_are_stored_with_the_complaint_and_do_not_change_the_rule_result(client):
    a, b = ("COM-SEED-6", "COM-SEED-7")
    r = _save(client, repeat_decisions=[{"prior_complaint_id": a, "decision": "reject", "reason": "Different container"},
                                        {"prior_complaint_id": b, "decision": "reject", "reason": "Fixed last week, new problem"}])
    assert r.status_code == 201 and r.json()["repeat"]["is_repeat"] is True                       # both disputed: the rule still says repeat
    rec = client.get(f"/api/complaints/{r.json()['id']}", headers=EMP).json()
    assert rec["repeat_detected"] is True and {d["prior_complaint_id"]: d["decision"] for d in rec["repeat_disputes"]} == {a: "reject", b: "reject"}
    assert json.loads(rec["repeat_disputes"][0]["evidence"])["is_repeat"] is True                    # the original evidence is kept beside it


def test_a_confirmation_needs_no_reason_a_dispute_does(client):
    before = _count()
    refused = _save(client, repeat_decisions=[{"prior_complaint_id": "COM-SEED-6", "decision": "reject", "reason": "  "}])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "reason_required"
    assert _count() == before                                                                      # nothing was saved, not even the complaint
    ok = _save(client, repeat_decisions=[{"prior_complaint_id": "COM-SEED-6", "decision": "confirm"}])
    d = client.get(f"/api/complaints/{ok.json()['id']}", headers=EMP).json()["repeat_disputes"]
    assert ok.status_code == 201 and d[0]["decision"] == "confirm" and d[0]["reason"] == "Confirmed by user"


def test_only_complaints_the_rule_linked_can_be_decided_and_nothing_is_half_saved(client):
    before = _count()
    r = _save(client, repeat_decisions=[{"prior_complaint_id": "COM-SEED-6", "decision": "confirm"},
                                        {"prior_complaint_id": "COM-SEED-1", "decision": "reject", "reason": "not even linked"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_repeat_decision" and _count() == before
    twice = _save(client, repeat_decisions=[{"prior_complaint_id": "COM-SEED-6", "decision": "confirm"}, {"prior_complaint_id": "COM-SEED-6", "decision": "confirm"}])
    assert twice.status_code == 422 and _count() == before


def test_a_later_dispute_on_the_endpoint_follows_the_same_rules(client):
    cid = _save(client).json()["id"]
    other = signed_in(client, "other.employee@example.nl", "sales")
    body = {"complaint_id": cid, "prior_complaint_id": "COM-SEED-6", "decision": "reject", "reason": "Different container"}
    assert client.post("/api/repeat-disputes", headers=other, json=body).json()["error"]["code"] == "not_your_complaint"     # not their complaint
    assert client.post("/api/repeat-disputes", headers=EMP, json={**body, "reason": ""}).json()["error"]["code"] == "reason_required"
    assert client.post("/api/repeat-disputes", headers=EMP, json={**body, "prior_complaint_id": "COM-SEED-1"}).json()["error"]["code"] == "not_a_linked_complaint"
    assert client.post("/api/repeat-disputes", headers=EMP, json=body).status_code == 201
    assert client.post("/api/repeat-disputes", headers=ADMIN, json={**body, "prior_complaint_id": "COM-SEED-7"}).status_code == 201   # an administrator can too


def test_the_rule_owner_reviews_who_decided_what_and_why(client):
    _save(client, repeat_decisions=[{"prior_complaint_id": "COM-SEED-6", "decision": "reject", "reason": "Different container"}])
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    item = client.get("/api/repeat-disputes", headers=juul).json()["items"][0]
    assert (item["decision"], item["reason"], item["prior_complaint_id"]) == ("reject", "Different container", "COM-SEED-6")
    assert item["actor_name"] and item["customer_name"] and item["site_name"] and item["rule_version"] and item["prior_cause"] and item["prior_created"]
    csv = client.get("/api/export/disputes.csv", headers=juul)
    assert csv.status_code == 200 and "Different container" in csv.text and csv.text.splitlines()[0].startswith("at,complaint_id")
    assert client.get("/api/export/disputes.csv", headers=EMP).status_code == 403                  # employees do not export the review list
