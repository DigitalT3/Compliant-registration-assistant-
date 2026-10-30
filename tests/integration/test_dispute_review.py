"""The weekly review of repeat decisions (FR-13 override): what is waiting, who may record the review, what it changes."""
from datetime import datetime, timedelta, timezone

from backend import db
from tests.conftest import ADMIN, EMP
from tests.integration.test_api_flow import BASE
from tests.integration.test_team_scope import signed_in

URL = "/api/repeat-disputes"


def two_linked(client):
    a = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed"}).json()["id"]
    b = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed"}).json()
    assert b["repeat"]["matches"][0]["id"] == a
    return b["id"], a


def decide(client, cid, prior, decision, reason):
    r = client.post(URL, headers=EMP, json={"complaint_id": cid, "prior_complaint_id": prior, "decision": decision, "reason": reason})
    assert r.status_code == 201, r.text


def test_nothing_waits_when_there_are_no_disputes(client):
    r = client.get(URL, headers=ADMIN).json()["review"]
    assert (r["pending"], r["due"], r["last_review_at"]) == (0, False, None)


def test_a_dispute_waits_and_is_due_until_reviewed(client):
    cid, prior = two_linked(client)
    decide(client, cid, prior, "reject", "different container")
    r = client.get(URL, headers=ADMIN).json()
    assert r["review"]["pending"] == 1 and r["review"]["due"] is True and r["items"][0]["reviewed_at"] is None
    done = client.post(URL + "/review", headers=ADMIN, json={"note": "week 44"})
    assert done.status_code == 200
    s = done.json()
    assert s["pending"] == 0 and s["due"] is False and s["last_review_by"] and s["next_due"]
    item = client.get(URL, headers=ADMIN).json()["items"][0]
    assert item["decision"] == "reject" and item["reason"] == "different container"        # the decision itself is untouched
    assert item["reviewed_at"] and item["review_note"] == "week 44" and item["reviewed_by_name"]
    assert any(r["action"] == "repeat_disputes_reviewed" for r in db_audit(client))


def db_audit(client):
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute("SELECT action FROM audit").fetchall()]
    finally:
        conn.close()


def test_confirmations_do_not_wait(client):
    cid, prior = two_linked(client)
    decide(client, cid, prior, "confirm", "")
    assert client.get(URL, headers=ADMIN).json()["review"]["pending"] == 0


def test_a_week_after_the_last_review_new_disputes_make_it_due_again(client):
    cid, prior = two_linked(client)
    client.post(URL + "/review", headers=ADMIN, json={})
    decide(client, cid, prior, "reject", "not the same")
    assert client.get(URL, headers=ADMIN).json()["review"] == {**client.get(URL, headers=ADMIN).json()["review"], "pending": 1, "due": False}   # reviewed today
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    conn = db.connect()
    conn.execute("UPDATE app_settings SET value=? WHERE key='dispute_review_last'", ('{"at": "%s", "by": "x", "note": null}' % old,))
    conn.commit(); conn.close()
    assert client.get(URL, headers=ADMIN).json()["review"]["due"] is True


def test_who_may_record_the_review(client):
    for headers in (EMP, {"X-Demo-User": "demo.evaluator"}, {"X-Demo-User": "demo.viewer"}):
        assert client.post(URL + "/review", headers=headers, json={}).status_code == 403
    juul = signed_in(client, "juul@example.nl", None, role="rule_owner")
    assert client.post(URL + "/review", headers=juul, json={}).status_code == 200
    assert client.post(URL + "/review", headers=ADMIN, json={}).status_code == 200


def test_the_csv_carries_the_review(client):
    cid, prior = two_linked(client)
    decide(client, cid, prior, "reject", "other site entrance")
    client.post(URL + "/review", headers=ADMIN, json={"note": "ok"})
    head, row = client.get("/api/export/disputes.csv", headers=ADMIN).text.strip().splitlines()[:2]
    assert head.endswith("reviewed_at,reviewed_by,review_note") and row.endswith(",ok")
