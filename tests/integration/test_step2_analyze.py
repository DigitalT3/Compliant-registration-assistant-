"""Gap-analysis step 2: single analyze call, per-type summary templates, AI timeout, live-provider contract."""
import json
import time

import pytest

from backend import settings
from backend.services import ai
from tests.conftest import EMP

SERVICE = "The container BOX-009-1 was not emptied on Tuesday, scheduled for the morning. It was missed again."
BILLING = "Invoice 12345 charged us twice, about €120,50 is disputed."


def analyze(client, text, **extra):
    r = client.post("/api/complaints/analyze", headers=EMP, json={"text": text, **extra})
    assert r.status_code == 200
    return r.json()


def test_one_call_returns_summary_and_classification(client):
    t0 = time.monotonic()
    out = analyze(client, SERVICE, language="en")
    assert time.monotonic() - t0 < 3                      # PRD: suggestions in <= 3 s
    assert out["ai_status"] == "ok" and out["mock"] is True
    cls, summ = out["result"]["classification"], out["result"]["summary"]
    assert cls["complaint_type"] == "service" and cls["candidates"][0]["root_cause_id"] == "missed"
    assert out["preselect"] == "missed" and out["low_confidence"] is False
    assert summ["what"] and summ["language"] == "en"
    assert summ["extras"]["container_no"] == "BOX-009-1"
    assert summ["extras"]["expected_vs_actual_service_date"].startswith("scheduled")


def test_template_follows_the_predicted_type(client):
    summ = analyze(client, BILLING, language="en")["result"]["summary"]
    assert set(summ["extras"]) == {"invoice_no", "amount_disputed"}
    assert summ["extras"]["invoice_no"] == "12345" and "120" in summ["extras"]["amount_disputed"]


def test_chosen_type_overrides_prediction_for_the_template(client):
    summ = analyze(client, SERVICE, complaint_type="conduct")["result"]["summary"]
    assert set(summ["extras"]) == {"who_or_vehicle_if_known"}


def test_summarise_uses_type_template(client):
    r = client.post("/api/complaints/summarise", headers=EMP, json={"text": BILLING, "complaint_type": "billing"}).json()
    assert set(r["result"]["extras"]) == {"invoice_no", "amount_disputed"}
    r = client.post("/api/complaints/summarise", headers=EMP, json={"text": BILLING}).json()
    assert r["result"]["extras"] == {}                    # no type chosen: no type-specific fields


def test_low_confidence_preselects_nothing_but_still_summarises(client):
    out = analyze(client, "Something odd happened but I am not sure what.")
    assert out["low_confidence"] is True and out["preselect"] is None
    assert out["result"]["summary"]["what"]


@pytest.mark.parametrize("mode", ["timeout", "unavailable", "invalid_json"])
def test_ai_faults_return_controlled_failure(client, monkeypatch, mode):
    monkeypatch.setenv("AI_MOCK_FAIL", mode)
    out = analyze(client, SERVICE)
    assert out["ai_status"] == "failed" and "continue manually" in out["message"]


def test_unknown_taxonomy_value_is_rejected(client):
    class Bad:
        name, mock, model = "bad", True, "bad"

        def complete_json(self, op, payload):
            return {"summary": {"language": "en"}, "classification": {
                "complaint_type": "service", "candidates": [{"root_cause_id": "made_up", "reason": "x", "confidence": 0.9}]}}

    ai.set_provider(Bad())
    out = analyze(client, SERVICE)
    assert out["ai_status"] == "failed" and out["error_category"] == "invalid_output"


def test_unknown_template_fields_are_dropped(client):
    class Extra:
        name, mock, model = "x", True, "x"

        def complete_json(self, op, payload):
            return {"summary": {"language": "en", "extras": {"container_no": "BOX-1", "secret_field": "leak"}},
                    "classification": {"complaint_type": "service", "candidates": []}}

    ai.set_provider(Extra())
    assert analyze(client, SERVICE, complaint_type="service")["result"]["summary"]["extras"] == {"container_no": "BOX-1"}


def test_outcome_is_logged_from_the_analyze_event(client):
    s = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    analyze(client, SERVICE, session_id=s)
    body = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
            "root_cause": "missed", "description": SERVICE, "session_id": s}
    assert client.post("/api/complaints", headers=EMP, json=body).status_code == 201
    m = client.get("/api/analytics/summary", headers={"X-Demo-User": "demo.admin"}).json()
    assert m["classification"]["top_three_rate"] == {"value": 1.0, "n": 1}
    assert m["ai"]["success_rate"]["n"] == 1


def test_timeout_budget_is_within_the_prd_target():
    ai_cfg = settings.ai_settings()
    assert ai_cfg["timeout_s"] <= 3.5 and ai_cfg["max_retries"] == 0


# ---- live provider contract (no network: httpx.post is replaced) ----------------------------------
class _Resp:
    def __init__(self, content):
        self._c = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "live")
    monkeypatch.setenv("AI_BASE_URL", "https://llm.example.eu/v1")
    monkeypatch.setenv("AI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AI_MODEL", "demo-model")


def test_live_request_carries_schema_taxonomy_and_untrusted_delimiters(client, live, monkeypatch):
    import httpx
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json, headers=headers, timeout=timeout)
        return _Resp(__import__("json").dumps({
            "summary": {"what": "Container not emptied", "language": "en", "extras": {"container_no": "BOX-009-1"}},
            "classification": {"complaint_type": "service",
                               "candidates": [{"root_cause_id": "missed", "reason": "not emptied", "confidence": 0.9}]}}))

    monkeypatch.setattr(httpx, "post", fake_post)
    out = analyze(client, SERVICE, complaint_type="service")
    assert out["ai_status"] == "ok" and out["mock"] is False and out["preselect"] == "missed"
    system, user = (m["content"] for m in seen["body"]["messages"])
    assert "$defs" in system or "properties" in system            # JSON schema is part of the prompt
    assert "untrusted" in system and user.startswith("<complaint>") and "</complaint>" in user
    assert "missed" in user and "template_extras_by_type" in user  # taxonomy and templates are sent
    assert seen["url"].endswith("/chat/completions") and seen["timeout"] <= 3.5
    assert seen["headers"]["Authorization"] == "Bearer test-key-not-real"


def test_live_timeout_and_garbage_fall_back(client, live, monkeypatch):
    import httpx

    def timeout(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "post", timeout)
    assert analyze(client, SERVICE)["error_category"] == "timeout"
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp("not json"))
    assert analyze(client, SERVICE)["ai_status"] == "failed"


# ---- Bedrock provider contract (no network: the boto3 client is replaced) --------------------------
class _FakeBedrock:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def converse(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


@pytest.fixture()
def bedrock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "eu.example-model")

    def install(fake):
        monkeypatch.setattr(ai.BedrockProvider, "_bedrock", lambda self, timeout=None: fake)
    return install


_GOOD = ('{"summary": {"what": "Container not emptied", "language": "en", "extras": {}}, "classification": '
         '{"complaint_type": "service", "candidates": [{"root_cause_id": "missed", "reason": "not emptied", "confidence": 0.9}]}}')


def test_bedrock_request_and_fenced_reply(client, bedrock):
    fake = _FakeBedrock("Here you go:\n```json\n" + _GOOD + "\n```")
    bedrock(fake)
    out = analyze(client, SERVICE, complaint_type="service")
    assert out["ai_status"] == "ok" and out["mock"] is False and out["provider"] == "bedrock" and out["preselect"] == "missed"
    call = fake.calls[0]
    assert call["modelId"] == "eu.example-model" and call["inferenceConfig"]["temperature"] == 0
    assert "untrusted" in call["system"][0]["text"]
    assert call["messages"][0]["content"][0]["text"].startswith("<complaint>")
    assert client.get("/health").json()["ai_region"] == "eu-central-1"


def test_bedrock_faults_fall_back(client, bedrock):
    from botocore.exceptions import ClientError, ReadTimeoutError
    bedrock(_FakeBedrock(error=ReadTimeoutError(endpoint_url="https://x")))
    assert analyze(client, SERVICE)["error_category"] == "timeout"
    bedrock(_FakeBedrock(error=ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse")))
    assert analyze(client, SERVICE)["error_category"] == "unavailable"
    bedrock(_FakeBedrock("no json here"))
    assert analyze(client, SERVICE)["error_category"] == "invalid_output"


def test_bedrock_where_falls_back_to_the_registered_site(client, bedrock):
    bedrock(_FakeBedrock(_GOOD))   # the model leaves "where" empty
    site = client.get("/api/customer-data/sites", headers=EMP).json()
    site = (site if isinstance(site, list) else site.get("rows") or site.get("items"))[0]
    out = client.post("/api/complaints/analyze", json={"text": "Container niet geleegd.", "site_id": site["id"]}, headers=EMP).json()
    assert out["result"]["summary"]["where"] == site["name"] and "where" not in out["result"]["summary"]["unknown_fields"]


def test_container_extra_is_filled_from_the_chosen_order(client):
    text = "De container is vandaag niet geleegd."   # names no container
    out = analyze(client, text, complaint_type="service", container="BOX-001-1")
    assert out["result"]["summary"]["extras"]["container_no"] == "BOX-001-1" and out["context_extras"] == ["container_no"]
    named = analyze(client, SERVICE, complaint_type="service", container="BOX-001-1")   # text names BOX-009-1: text wins
    assert named["result"]["summary"]["extras"]["container_no"] == "BOX-009-1" and "context_extras" not in named
    billing = analyze(client, BILLING, complaint_type="billing", container="BOX-001-1")   # no container field for billing
    assert "container_no" not in billing["result"]["summary"]["extras"]
