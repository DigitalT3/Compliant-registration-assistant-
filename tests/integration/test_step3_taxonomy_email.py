"""Gap-analysis step 3: two-level taxonomy (FR-11), email extraction (FR-02), repeat decisions (FR-13)."""
import json

from backend import db
from backend.settings import get_config
from tests.conftest import ADMIN, EMP


def test_taxonomy_is_two_level_and_consistent():
    cfg = get_config()
    cats = {c["id"] for c in cfg["root_cause_categories"]}
    types = {t["id"] for t in cfg["types"]}
    assert len(cfg["root_causes"]) >= 11 and len(cats) >= 7
    for c in cfg["root_causes"]:
        assert c["level1"] in cats, c["id"]                 # every cause sits in a category
        assert c["type"] is None or c["type"] in types      # and maps to a complaint type (or none for Other)
    assert len({c["level1"] for c in cfg["root_causes"]}) > len(types)   # categories are finer than types
    assert cfg["taxonomy_version"] == "provisional-taxonomy-v2"
    assert cfg["repeat_rule"]["cause_mode"] == "level1"                  # PRD section 9 / plan draft default


def test_both_levels_are_stored_on_save_and_seed(client):
    body = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
            "root_cause": "late", "description": "Collection was late."}
    rec = client.get(f"/api/complaints/{client.post('/api/complaints', headers=EMP, json=body).json()['id']}",
                     headers=EMP).json()
    assert (rec["root_cause"], rec["root_cause_category"]) == ("late", "collection")
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM complaints WHERE root_cause_category IS NULL").fetchone()[0] == 0


def _check(client, cause):
    return client.post("/api/complaints/check-repeat", headers=EMP,
                       json={"customer_id": "C001", "site_id": "C001-S1", "root_cause": cause}).json()


def test_repeat_cause_match_level_is_configurable(client):
    # Seeded history at C001-S1: "missed" (collection), 5 days ago.
    assert _check(client, "late")["is_repeat"] is True            # level1: same category "collection"
    assert _check(client, "damage")["is_repeat"] is False         # different category
    rule = {k: v for k, v in get_config()["repeat_rule"].items() if k not in ("version", "last_updated")}
    rule["cause_mode"] = "level2"
    assert client.put("/api/config/repeat-rule", headers=ADMIN, json=rule).status_code == 200
    assert _check(client, "late")["is_repeat"] is False           # level2: sub-cause must match
    assert _check(client, "missed")["is_repeat"] is True


def test_new_causes_are_suggested(client):
    def top(text):
        r = client.post("/api/complaints/classify", headers=EMP, json={"text": text}).json()
        return r["result"]["candidates"][0]["root_cause_id"], r["result"]["complaint_type"]

    assert top("Waste was spilled all over the road after emptying.") == ("spillage", "service")
    assert top("The truck damaged our gate while turning.")[0] == "property_damage"
    assert top("The weight on the weighing ticket is wrong.") == ("weighing", "billing")


def test_email_extraction_drops_headers_and_validates_identifiers(client):
    email = ("From: planning@example.nl\nTo: klantenservice@example.nl\nSubject: Klacht\n\n"
             "Goedemorgen, onze container BOX-009-1 is vandaag niet geleegd. Klantnummer 100009. Graag een oplossing.")
    x = client.post("/api/complaints/extract", headers=EMP, json={"text": email}).json()["result"]
    assert x["customer_number"] == "100009" and x["container"] == "BOX-009-1" and x["language"] == "nl"
    assert "Subject" not in x["description"] and "niet geleegd" in x["description"]
    assert x["validation"] == {"customer_number": True, "order_reference": None, "container": True}


def test_email_with_unknown_identifier_is_flagged_not_trusted(client):
    r = client.post("/api/complaints/extract", headers=EMP,
                    json={"text": "Container BOX-999-9 niet geleegd, klant 100999."}).json()
    assert r["result"]["validation"]["customer_number"] is False and r["result"]["validation"]["container"] is False


def test_repeat_decision_is_stored_without_changing_the_rule_outcome(client):
    saved = client.post("/api/complaints", headers=EMP, json={
        "customer_id": "C001", "site_id": "C001-S1", "channel": "phone", "complaint_type": "service",
        "root_cause": "missed", "description": "Missed again."}).json()
    assert saved["repeat"]["is_repeat"] is True and saved["repeat"]["matches"][0]["id"] == "POC-SEED-1"
    d = client.post("/api/repeat-disputes", headers=EMP, json={
        "complaint_id": saved["id"], "prior_complaint_id": "POC-SEED-1", "decision": "reject",
        "reason": "different container"}).json()
    assert d["rule_outcome_unchanged"] is True
    rec = client.get(f"/api/complaints/{saved['id']}", headers=EMP).json()
    assert rec["repeat_detected"] is True and rec["repeat_disputes"][0]["prior_complaint_id"] == "POC-SEED-1"
    assert json.loads(rec["repeat_disputes"][0]["evidence"])["is_repeat"] is True     # original evidence kept
