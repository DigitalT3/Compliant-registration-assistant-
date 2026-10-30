"""FR-14: the saved record maps one-to-one to the target field list (the names are placeholders until the complaint-system owner supplies theirs)."""
import json

from backend import db
from backend.services import complaints, field_mapping as fm
from tests.conftest import EMP

ORDER = {"customer_id": "C009", "site_id": "C009-S1", "contract_id": "C009-K1", "order_id": "C009-O10", "channel": "email", "complaint_type": "billing",
         "root_cause": "other", "other_reason": "Seagull nest under the lid", "language": "nl", "priority": "high", "owner_team": "sales",
         "description": "Café 'De Ruiter' – €45,50 te veel gefactureerd.\r\nTweede regel  "}


def _columns():
    with db.connect() as conn:
        return list(dict(conn.execute("SELECT * FROM complaints LIMIT 1").fetchone()).keys())


def test_every_stored_column_is_mapped_or_excluded_with_a_reason_and_nothing_twice():
    assert fm.check(_columns()) == []


def test_a_column_added_without_the_mapping_is_caught():
    assert fm.check(_columns() + ["new_column"]) == ["stored but neither mapped nor excluded: new_column"]
    broken = fm.load()
    broken["fields"].append({**broken["fields"][0], "poc_field": "ghost"})                    # same target field again, and not stored
    assert {"target field used twice: PROVISIONAL_ComplaintId", "mapped but not stored: ghost"} <= set(fm.check(_columns(), broken))


def test_the_target_names_are_marked_as_placeholders():
    m = fm.load()
    assert m["validated"] is False and all(f["target_field"].startswith("PROVISIONAL_") for f in m["fields"])


def test_a_saved_record_arrives_in_the_target_structure_exactly_as_entered(client):
    saved = client.post("/api/complaints", headers=EMP, json=ORDER).json()
    out = client.get(f"/api/complaints/{saved['id']}/target", headers=EMP).json()
    t = out["record"]
    assert list(t) == [f["target_field"] for f in fm.load()["fields"]]                       # exactly the target fields, in the order of the list
    assert out["missing_required"] == [] and out["validated"] is False
    assert (t["PROVISIONAL_ComplaintId"], t["PROVISIONAL_Account"], t["PROVISIONAL_Site"], t["PROVISIONAL_Contract"], t["PROVISIONAL_Order"]) == \
           (saved["id"], "C009", "C009-S1", "C009-K1", "C009-O10")
    assert t["PROVISIONAL_Description"] == ORDER["description"]                               # as typed, byte for byte
    assert (t["PROVISIONAL_Channel"], t["PROVISIONAL_Type"], t["PROVISIONAL_RootCause"], t["PROVISIONAL_OtherReason"], t["PROVISIONAL_Language"]) == \
           ("email", "billing", "other", "Seagull nest under the lid", "nl")
    assert (t["PROVISIONAL_Priority"], t["PROVISIONAL_OwnerTeam"], t["PROVISIONAL_Status"]) == ("high", "sales", "open")
    assert t["PROVISIONAL_Container"] == "BOX-009-1" and t["PROVISIONAL_RootCauseCategory"] == "other"            # read from the order / derived from the cause
    assert t["PROVISIONAL_RegisteredBy"] == "demo.emp.a1" and t["PROVISIONAL_RegistrationDate"] and t["PROVISIONAL_RepeatRuleVersion"] and t["PROVISIONAL_TaxonomyVersion"]


def test_the_mapping_loses_nothing_and_adds_nothing(client):
    cid = client.post("/api/complaints", headers=EMP, json=ORDER).json()["id"]
    with db.connect() as conn:
        rec = complaints.get(conn, cid)
    mapped = [f["poc_field"] for f in fm.load()["fields"]]
    back = fm.from_target(fm.to_target(rec))
    assert back == {k: rec[k] for k in mapped}                                              # target -> PoC gives back every mapped value
    assert len(set(fm.to_target(rec))) == len(mapped) == len(set(mapped))                    # one target field per PoC field, no more, no fewer


def test_every_seeded_and_saved_complaint_fills_the_required_target_fields(client):
    client.post("/api/complaints", headers=EMP, json=ORDER)
    with db.connect() as conn:
        rows = [complaints._row(r) for r in conn.execute("SELECT * FROM complaints")]
    assert len(rows) > 40
    assert [r["id"] for r in rows if fm.missing_required(fm.to_target(r))] == []


def test_the_endpoint_describes_the_mapping_and_says_it_is_one_to_one(client):
    m = client.get("/api/field-mapping", headers=EMP).json()
    assert m["one_to_one"] is True and m["problems"] == [] and m["validated"] is False
    assert len(m["fields"]) + len(m["not_mapped"]) == 30 and len(m["fields"]) == 23 and set(m["not_mapped"]) == {"created", "session_id", "payload", "summary_meta", "scenario", "is_poc", "is_seed"}
    assert client.get("/api/complaints/NOPE/target", headers=EMP).status_code == 404
    assert client.get("/api/field-mapping").status_code == 401
