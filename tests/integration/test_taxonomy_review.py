"""Agreeing the root-cause list ("agree v1"): who may review, when the list counts as agreed, and what resets it."""
import copy

from backend import db
from backend.services import taxonomy_review
from tests.conftest import ADMIN, EMP
from tests.integration.test_step4_usertest import LEAD
from tests.integration.test_team_scope import signed_in

URL = "/api/config/root-causes"


def owners(client):
    """Three process owners with their own accounts (role evaluator), signed in with their own passwords."""
    return [signed_in(client, f"{n}@example.nl", None, role="evaluator") for n in ("kwafie", "naomi", "maikel")]


def state(client):
    return client.get(URL).json()["review"]


def test_the_list_starts_as_a_draft(client):
    r = state(client)
    assert (r["state"], r["agreed"], r["required"], r["reviews"], r["agreed_at"]) == ("draft", 0, 3, [], None)
    assert len(r["content_hash"]) == 12
    assert client.get("/api/config").json()["taxonomy_review"] == {"state": "draft", "required": 3, "agreed": 0}


def test_only_the_process_owners_can_review(client):
    body = {"decision": "agree"}
    for headers in (EMP, LEAD, ADMIN, {"X-Demo-User": "demo.viewer"}):
        assert client.post(URL + "/review", headers=headers, json=body).status_code == 403
    assert client.post(URL + "/review", json=body).status_code == 401                        # not signed in
    assert client.post(URL + "/review", headers={"X-Demo-User": "demo.evaluator"}, json=body).status_code == 200
    assert client.post(URL + "/review", headers={"X-Demo-User": "demo.evaluator"}, json={"decision": "maybe"}).status_code == 422


def test_three_agreements_make_the_list_agreed(client):
    kwafie, naomi, maikel = owners(client)
    assert client.post(URL + "/review", headers=kwafie, json={"decision": "agree"}).json()["agreed"] == 1
    again = client.post(URL + "/review", headers=kwafie, json={"decision": "agree"}).json()   # the same person twice counts once
    assert again["agreed"] == 1 and again["state"] == "draft" and len(again["reviews"]) == 1
    client.post(URL + "/review", headers=naomi, json={"decision": "agree"})
    done = client.post(URL + "/review", headers=maikel, json={"decision": "agree"}).json()
    assert done["state"] == "agreed" and done["agreed"] == 3 and done["agreed_at"]
    assert {r["name"] for r in done["reviews"]} == {"Test Kwafie", "Test Naomi", "Test Maikel"}
    assert state(client)["state"] == "agreed" and client.get("/api/config").json()["taxonomy_review"]["state"] == "agreed"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit WHERE action='taxonomy_agreed'").fetchone()[0] == 4


def test_a_request_for_changes_blocks_until_that_person_agrees(client):
    kwafie, naomi, maikel = owners(client)
    for h in (kwafie, naomi, maikel):
        client.post(URL + "/review", headers=h, json={"decision": "agree"})
    assert state(client)["state"] == "agreed"
    assert client.post(URL + "/review", headers=maikel, json={"decision": "changes"}).json()["error"]["code"] == "comment_required"
    r = client.post(URL + "/review", headers=maikel, json={"decision": "changes", "comment": "Split 'Other' into two"}).json()
    assert r["state"] == "changes_requested" and r["agreed"] == 2                            # three had agreed, one changed their mind
    assert next(x for x in r["reviews"] if x["name"] == "Test Maikel")["comment"] == "Split 'Other' into two"
    assert client.post(URL + "/review", headers=maikel, json={"decision": "agree"}).json()["state"] == "agreed"


def test_changing_the_list_resets_the_agreement(client, monkeypatch):
    for h in owners(client):
        client.post(URL + "/review", headers=h, json={"decision": "agree"})
    assert state(client)["state"] == "agreed"
    cfg = copy.deepcopy(taxonomy_review.get_config())
    cfg["root_causes"][0]["definition"] = "A different definition"                           # the list changed after they agreed
    monkeypatch.setattr(taxonomy_review, "get_config", lambda: cfg)
    with db.connect() as conn:
        s = taxonomy_review.status(conn)
    assert s["state"] == "draft" and s["agreed"] == 0                                        # nobody agreed to THIS list
    assert len(s["reviews"]) == 3 and not any(r["current"] for r in s["reviews"])           # their reviews stay as history
    assert taxonomy_review.content_hash(cfg) != taxonomy_review.content_hash(copy.deepcopy(cfg) | {"root_causes": copy.deepcopy(cfg["root_causes"])[:-1]})
