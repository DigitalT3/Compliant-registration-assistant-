"""Making an agreed proposed list the live cause list: the mapping, the backup and the freeze."""
import json

from backend import db
from backend.services import root_cause_analysis as rca
from tests.conftest import ADMIN, EMP
from tests.integration.test_root_cause_analysis import TEXTS
from tests.integration.test_taxonomy_review import owners


def proposal(client):
    """Themes and a proposal built from invented 'Other' reasons (mock assistant)."""
    conn = db.connect()
    for r, t in zip(conn.execute("SELECT id FROM complaints LIMIT 7").fetchall(), TEXTS):
        conn.execute("UPDATE complaints SET root_cause='other', other_reason=? WHERE id=?", (t, r["id"]))
    conn.commit(); conn.close()
    client.post("/api/rca/themes", headers=ADMIN, json={"min_theme_size": 2})
    return client.post("/api/rca/proposal", headers=ADMIN, json={"max_categories": 6}).json()


def agree_all(client):
    hs = owners(client)
    for h in hs:
        client.post("/api/rca/proposal/review", headers=h, json={"decision": "agree"})
    return hs


def live(client):
    return client.get("/api/config/root-causes").json()


def test_cannot_apply_until_everyone_agreed_and_only_the_right_roles_may(client):
    proposal(client)
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).status_code == 409           # not agreed yet
    st = client.get("/api/rca/live", headers=ADMIN).json()
    assert not st["can_apply"] and "not_agreed" in st["blockers"]
    agree_all(client)
    assert client.post("/api/rca/proposal/apply", headers=EMP, json={}).status_code == 403
    assert client.get("/api/rca/live", headers=ADMIN).json()["can_apply"] is True


def test_applying_makes_the_proposal_live_and_old_causes_keep_working(client):
    prop = proposal(client)
    before = live(client)
    hs = agree_all(client)
    done = client.post("/api/rca/proposal/apply", headers=hs[0], json={"note": "test"})            # a process owner may apply it
    assert done.status_code == 200
    now = live(client)
    assert {c["id"] for c in now["root_causes"]} == {c["id"] for c in prop["categories"]}
    assert now["taxonomy_version"] == f"live-{prop['version']}" and len(now["root_causes"]) < len(before["root_causes"])
    retired = {c["id"]: c for c in now["retired_causes"]}
    old_ids = {c["id"] for c in before["root_causes"]} - {c["id"] for c in now["root_causes"]}
    assert old_ids and old_ids <= set(retired)
    live_ids = {c["id"] for c in now["root_causes"]}
    assert all(c["merged_into"] in live_ids and c["retired"] for c in retired.values())             # each one points at the category that replaced it
    st = client.get("/api/rca/live", headers=ADMIN).json()
    assert "already_live" in st["blockers"]
    assert now["review"]["state"] == "agreed" and now["review"]["agreed"] == 3                      # the agreement carries over, no second round
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).status_code == 409


def test_a_retired_cause_cannot_be_chosen_for_a_new_registration(client):
    proposal(client)
    agree_all(client)
    client.post("/api/rca/proposal/apply", headers=ADMIN, json={})
    gone = live(client)["retired_causes"][0]["id"]
    r = client.post("/api/complaints", headers=EMP, json={"customer_id": "100001", "site_id": "C001-S1", "contract_id": "C001-K1", "complaint_type": "service",
                                                          "description": "x y z test", "root_cause": gone})
    assert r.status_code == 422 and r.json()["error"]["code"] in ("invalid_root_cause", "missing_required_fields")


def test_restore_brings_the_previous_list_and_its_agreements_back(client):
    proposal(client)
    agree_all(client)
    original = live(client)
    client.post("/api/rca/proposal/apply", headers=ADMIN, json={})
    assert client.post("/api/rca/live/restore", headers=EMP, json={}).status_code == 403
    back = client.post("/api/rca/live/restore", headers=ADMIN, json={"note": "undo"})
    assert back.status_code == 200
    now = live(client)
    assert [c["id"] for c in now["root_causes"]] == [c["id"] for c in original["root_causes"]] and not now["retired_causes"]
    assert now["taxonomy_version"] == original["taxonomy_version"]
    assert client.post("/api/rca/live/restore", headers=ADMIN, json={}).status_code == 409           # the original is already live


def test_a_frozen_list_cannot_be_changed(client):
    proposal(client)
    agree_all(client)
    assert client.put("/api/rca/live/freeze", headers=EMP, json={"frozen": True}).status_code == 403
    assert client.put("/api/rca/live/freeze", headers=ADMIN, json={"frozen": True, "note": "user test"}).json()["freeze"]["frozen"] is True
    st = client.get("/api/rca/live", headers=ADMIN).json()
    assert "frozen" in st["blockers"] and not st["can_apply"]
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).json()["error"]["code"] == "list_frozen"
    client.put("/api/rca/live/freeze", headers=ADMIN, json={"frozen": False})
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).status_code == 200


def test_it_waits_while_somebody_is_registering(client):
    proposal(client)
    agree_all(client)
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    assert "registration_in_progress" in client.get("/api/rca/live", headers=ADMIN).json()["blockers"]
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).json()["error"]["code"] == "registration_in_progress"
    client.post(f"/api/sessions/{sid}/complete", headers=EMP, json={"outcome": "abandoned"})
    assert client.post("/api/rca/proposal/apply", headers=ADMIN, json={}).status_code == 200


def test_the_repeat_rule_sees_a_retired_cause_in_its_replacement(client):
    from backend.settings import causes_by_id, get_config
    proposal(client)
    agree_all(client)
    client.post("/api/rca/proposal/apply", headers=ADMIN, json={})
    cfg = get_config()
    for r in cfg["retired_causes"]:
        target = causes_by_id(cfg)[r["merged_into"]]
        assert (r["level1"], r["level2"]) == (target["level1"], target["level2"])


def test_the_catch_all_other_stays_live_even_when_the_proposal_leaves_it_out():
    from backend.services import taxonomy_apply
    from backend.settings import get_config
    cfg = get_config()
    prop = {"categories": [{"id": "collection", "name_en": "Collection", "name_nl": "Ophaling", "definition": "d", "examples": ["a", "b"],
                            "covers_existing": ["missed", "late", "access"], "covers_themes": []},
                           {"id": "billing", "name_en": "Billing", "name_nl": "Facturatie", "definition": "d", "examples": ["a", "b"],
                            "covers_existing": ["invoice", "weighing"], "covers_themes": []}]}
    built = taxonomy_apply.build_live(cfg, prop)
    ids = {c["id"] for c in built["root_causes"]}
    assert "other" in ids and {c["id"] for c in built["root_cause_categories"]} >= {"other"}
    retired = {c["id"]: c["merged_into"] for c in built["retired_causes"]}
    assert "other" not in retired and retired["missed"] == "collection" and retired["invoice"] == "billing"
    assert retired["conduct"] == "other"                              # a cause the proposal did not place goes to the catch-all, not to a random category
