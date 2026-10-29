"""STEP-02 validation: lookup, prefill, AI fallback, save atomicity, roles, analytics."""
import os
import time

from tests.conftest import ADMIN, EMP

BASE = dict(customer_id="C009", site_id="C009-S1", channel="phone", complaint_type="service", description="d")


def test_lookup_cases(client):
    g = lambda q: client.get("/api/customers/search", params={"q": q}, headers=EMP).json()
    t0 = time.time()
    assert g("100009")["match_type"] == "customer_number"
    # 2 s on local SQLite; a remote database adds ~250 ms per query from a laptop, so allow more there
    assert time.time() - t0 < (10 if os.environ.get("POC_TEST_PG") == "1" else 2)
    assert g("ORD-002-10")["candidates"][0]["matched_site_id"] == "C002-S1"
    assert g("BOX-004-2")["candidates"][0]["matched_site_id"] == "C004-S2"
    amb = g("Delta Works")
    assert amb["ambiguous"] and amb["count"] == 2
    assert g("999999")["match_type"] == "none"
    assert client.get("/api/customers/search", params={"q": "100009"}).status_code == 401


def test_context_and_prefill(client):
    ctx = client.get("/api/customers/C003/context", headers=EMP).json()
    assert len(ctx["sites"]) == 3 and len(ctx["orders"]) <= 10
    r = client.post("/api/prefill", headers=EMP, json={"customer_id": "C003", "complaint_type": "billing"}).json()["fields"]
    assert r["site_id"]["provenance"] == "blank"  # ambiguous site never guessed
    assert r["channel"] == {"value": "email", "provenance": "default"}
    r = client.post("/api/prefill", headers=EMP, json={
        "customer_id": "C021", "complaint_type": "billing",
        "current_fields": {"channel": {"value": "phone", "provenance": "manual"}}}).json()["fields"]
    assert r["channel"]["value"] == "phone" and r["site_id"]["value"] == "C021-S1"


def test_classify_variants(client):
    c = lambda t: client.post("/api/complaints/classify", headers=EMP, json={"text": t}).json()
    a = c("The container was not emptied, it was missed again.")
    assert a["mock"] and a["preselect"] == "missed" and not a["low_confidence"]
    b = c("Something odd happened but I am not sure what.")
    assert b["low_confidence"] and b["preselect"] is None
    assert c("De factuur klopt niet.")["result"]["candidates"][0]["root_cause_id"] == "invoice"


def test_ai_failures_do_not_block(client, monkeypatch):
    for mode in ("timeout", "invalid_json", "unavailable"):
        monkeypatch.setenv("AI_MOCK_FAIL", mode)
        out = client.post("/api/complaints/summarise", headers=EMP, json={"text": "x"}).json()
        assert out["ai_status"] == "failed"
        assert out["error_category"] in ("timeout", "invalid_output", "unavailable")
    monkeypatch.delenv("AI_MOCK_FAIL")
    assert client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed"}).status_code == 201


def test_save_rules_and_retrieval(client):
    r = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "other"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "other_reason_required"
    assert client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "bogus"}).status_code == 422
    cid = client.post("/api/complaints", headers=EMP,
                      json={**BASE, "root_cause": "other", "other_reason": "seagull"}).json()["id"]
    got = client.get(f"/api/complaints/{cid}", headers=EMP).json()
    assert got["is_poc"] == 1 and got["repeat_checks"][0]["rule_version"]
    r2 = client.post("/api/complaints", headers=EMP,
                     json={**BASE, "root_cause": "other", "other_reason": "x"}).json()
    assert r2["repeat"]["is_repeat"] and r2["repeat"]["matches"][0]["id"] == cid
    assert client.get("/api/complaints", headers=EMP, params={"page_size": 5}).json()["total"] >= 17


def test_atomic_rollback(client, monkeypatch):
    from backend.services import complaints

    def boom(*a, **k):
        raise RuntimeError("forced")

    s = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    with monkeypatch.context() as m:
        m.setattr(complaints, "_insert_repeat_check", boom)
        r = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed", "session_id": s})
    assert r.status_code == 500 and "Traceback" not in r.text
    assert client.get("/api/complaints", headers=EMP, params={"include_seed": False}).json()["total"] == 0


def test_roles(client):
    assert client.get("/api/analytics/summary", headers=EMP).status_code == 403
    assert client.put("/api/config/repeat-rule", headers=EMP, json={}).status_code == 403
    assert client.post("/api/complaints", headers={"X-Demo-User": "demo.viewer"}, json={}).status_code == 403
    rule = dict(enabled=True, lookback_days=30, match_keys=["customer_id"], cause_mode="level1",
                eligible_statuses=["open"], missing_values="no_match")
    r = client.put("/api/config/repeat-rule", headers=ADMIN, json=rule)
    assert r.status_code == 200 and "edit" in r.json()["repeat_rule"]["version"]
    assert client.get("/api/config/repeat-rule").json()["repeat_rule"]["lookback_days"] == 30


def test_error_envelope(client):
    r = client.post("/api/complaints/classify", headers=EMP, json={})
    assert r.status_code == 422 and r.json()["error"]["request_id"]


def test_session_analytics(client):
    h = EMP
    assert client.get("/api/analytics/summary", headers=ADMIN).json()["empty"] is True
    s = client.post("/api/sessions", headers=h, json={"scenario": "T01"}).json()["session_id"]
    ev = lambda **k: client.post(f"/api/sessions/{s}/events", headers=h, json=k).status_code
    assert ev(type="field", field="site_id", origin="prefilled") == 200
    assert ev(type="field", field="channel", origin="default") == 200
    assert ev(type="field", field="x", origin="bogus") == 422
    ev(type="step_completed", step="find_customer")
    ev(type="step_entered", step="classify")
    client.post("/api/complaints/classify", headers=h, json={"text": "missed again", "session_id": s})
    assert client.post(f"/api/sessions/{s}/complete", headers=h, json={"outcome": "saved"}).status_code == 400
    prov = {"customer_id": "prefilled", "site_id": "prefilled", "channel": "default", "status": "default",
            "complaint_type": "suggested", "root_cause": "manual", "description": "manual"}
    body = {**BASE, "root_cause": "missed", "session_id": s, "field_provenance": prov}
    assert client.post("/api/complaints", headers=h, json=body).status_code == 201
    assert ev(type="step_entered", step="classify") == 409
    m = client.get("/api/analytics/summary", headers=ADMIN).json()
    assert m["sessions"]["saved"] == 1 and m["duration_seconds"]["n"] == 1
    assert m["classification"]["top_three_rate"] == {"value": 1.0, "n": 1}
    # 15 tracked fields; customer, site, channel and status were prefilled/defaulted, the rest blank or typed.
    assert m["fields"]["prefill_rate"] == {"value": round(4 / 15, 4), "n": 15}
    assert client.get("/api/analytics/sessions", headers=ADMIN).json()["total"] == 1
    assert client.get("/api/analytics/summary", headers=ADMIN, params={"root_cause": "late"}).json()["empty"] is True


def test_disputes_extract_eval(client):
    cid = client.post("/api/complaints", headers=EMP, json={**BASE, "root_cause": "missed"}).json()["id"]
    d = client.post("/api/repeat-disputes", headers=EMP,
                    json={"complaint_id": cid, "decision": "reject", "reason": "different issue"})
    assert d.status_code == 201
    assert client.get("/api/repeat-disputes", headers=EMP).json()["items"][0]["evidence"]
    x = client.post("/api/complaints/extract", headers=EMP,
                    json={"text": "From a@b.nl customer 100009 box BOX-009-1"}).json()
    assert x["result"]["validation"]["customer_number"] is True
    ev = {"X-Demo-User": "demo.evaluator"}
    assert client.post("/api/evaluations", headers=ev,
                       json={"complaint_id": cid, "usable": True, "expert_cause": "missed"}).status_code == 201
    assert client.get("/api/evaluations", headers=ev).json()["expert_agreement"] == {"value": 1.0, "n": 1}
    assert client.get("/openapi.json").status_code == 200 and client.get("/health").json()["ai_mock"]
