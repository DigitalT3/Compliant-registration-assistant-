"""Scripted synthetic acceptance scenarios T01-T10 (FR-01, FR-03, FR-07..FR-10, FR-12, FR-14).

These API-level tests validate the backend contracts used by the six-step browser
wizard. They deliberately use only deterministic synthetic seed data and the
explicitly labelled mock AI provider; browser automation remains unconfigured.
"""
from __future__ import annotations

import pytest

from tests.conftest import EMP


def _search(client, query: str) -> dict:
    """Return the authenticated customer-search response for a scripted query."""
    response = client.get("/api/customers/search", params={"q": query}, headers=EMP)
    assert response.status_code == 200
    return response.json()


def _candidate(client, query: str) -> dict:
    """Return the sole scripted lookup candidate, failing clearly for ambiguity."""
    result = _search(client, query)
    assert result["count"] == 1
    return result["candidates"][0]


def _complaint_payload(candidate: dict, root_cause: str, description: str, **extra: object) -> dict:
    """Build the minimum valid PoC-only registration payload for a selected record."""
    return {
        "customer_id": candidate["customer_id"],
        "site_id": candidate.get("matched_site_id") or f"{candidate['customer_id']}-S1",
        "channel": "phone",
        "complaint_type": "service",
        "root_cause": root_cause,
        "description": description,
        **extra,
    }


# FR-01, FR-04, FR-07, FR-14 / T01
def test_t01_basic_english_complaint_can_be_saved_and_retrieved(client):
    """T01: customer-number lookup through PoC-only complaint persistence."""
    scenario = _candidate(client, "100009")
    summary = client.post(
        "/api/complaints/summarise",
        headers=EMP,
        json={
            "text": "The container at our depot was not emptied on Tuesday, it was missed again.",
            "language": "en",
            "site_id": scenario["matched_site_id"],
        },
    )
    assert summary.status_code == 200
    assert summary.json()["ai_status"] == "ok"

    saved = client.post(
        "/api/complaints",
        headers=EMP,
        json=_complaint_payload(
            scenario,
            "missed",
            "The container at our depot was not emptied on Tuesday, it was missed again.",
            language="en",
            summary=summary.json()["result"],
            summary_meta={"mock": summary.json()["mock"]},
            scenario="T01",
        ),
    )
    assert saved.status_code == 201
    complaint_id = saved.json()["id"]

    detail = client.get(f"/api/complaints/{complaint_id}", headers=EMP)
    assert detail.status_code == 200
    assert detail.json()["customer_id"] == "C009"
    assert detail.json()["root_cause"] == "missed"
    assert detail.json()["is_poc"] == 1


# FR-01, FR-03 / T02
def test_t02_order_lookup_returns_associated_context(client):
    """T02: an order reference resolves its associated synthetic customer and site."""
    result = _search(client, "ORD-002-10")

    assert result["match_type"] == "order"
    assert result["count"] == 1
    assert result["candidates"][0]["number"] == "100002"
    assert result["candidates"][0]["matched_site_id"] == "C002-S1"

    context = client.get("/api/customers/C002/context", headers=EMP)
    assert context.status_code == 200
    assert any(order["reference"] == "ORD-002-10" for order in context.json()["orders"])


# FR-01, FR-03 / T03
def test_t03_container_lookup_returns_associated_context(client):
    """T03: a container reference resolves the correct customer and site."""
    result = _search(client, "BOX-004-2")

    assert result["match_type"] == "container"
    assert result["count"] == 1
    assert result["candidates"][0]["number"] == "100004"
    assert result["candidates"][0]["matched_site_id"] == "C004-S2"


# FR-01 / T04
def test_t04_ambiguous_name_requires_candidate_selection(client):
    """T04: partial-name matches remain ambiguous rather than being auto-selected."""
    result = _search(client, "Delta Works")

    assert result["match_type"] == "name"
    assert result["ambiguous"] is True
    assert result["count"] == 2
    assert {candidate["number"] for candidate in result["candidates"]} == {"100001", "100002"}


# FR-01 / T05
def test_t05_unknown_identifier_returns_explicit_no_match(client):
    """T05: an unknown identifier produces an empty, explicit no-match response."""
    result = _search(client, "999999")

    assert result["match_type"] == "none"
    assert result["count"] == 0
    assert result["candidates"] == []


# FR-07, FR-08 / T06
def test_t06_dutch_text_is_preserved_and_summarised(client):
    """T06: Dutch source text is preserved and receives a validated editable summary."""
    text = "Onze container is vandaag niet geleegd, de inzameling is gemist."
    response = client.post(
        "/api/complaints/summarise",
        headers=EMP,
        json={"text": text, "language": "nl", "site_id": "C009-S1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "ok"
    assert body["result"]["language"] == "nl"
    assert set(body["result"]).issuperset({"what", "where", "when", "impact"})


# FR-07, FR-08, FR-09 / T07
def test_t07_english_invoice_complaint_suggests_invoice_cause(client):
    """T07: English complaint text is classified through the configured mock provider."""
    text = "We were charged twice on the latest invoice."
    summary = client.post(
        "/api/complaints/summarise",
        headers=EMP,
        json={"text": text, "language": "en"},
    )
    classification = client.post(
        "/api/complaints/classify",
        headers=EMP,
        json={"text": text, "language": "en", "summary": summary.json()["result"]},
    )

    assert summary.status_code == 200
    assert classification.status_code == 200
    body = classification.json()
    assert body["ai_status"] == "ok"
    assert body["result"]["candidates"][0]["root_cause_id"] == "invoice"
    assert body["preselect"] == "invoice"


# FR-09 / T08
def test_t08_low_confidence_classification_never_preselects_a_cause(client):
    """T08: uncertain text prompts an explicit employee choice."""
    response = client.post(
        "/api/complaints/classify",
        headers=EMP,
        json={"text": "Something odd happened but I am not sure what.", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["low_confidence"] is True
    assert response.json()["preselect"] is None


# FR-10 / T09
def test_t09_other_cause_requires_reason_before_save(client):
    """T09: Other cannot be persisted until an explanatory reason is supplied."""
    candidate = _candidate(client, "100020")
    payload = _complaint_payload(
        candidate,
        "other",
        "A seagull built a nest under the lid of our container.",
        language="en",
    )

    rejected = client.post("/api/complaints", headers=EMP, json=payload)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "other_reason_required"

    saved = client.post(
        "/api/complaints",
        headers=EMP,
        json={**payload, "other_reason": "Wildlife obstruction is not represented by the provisional taxonomy."},
    )
    assert saved.status_code == 201
    assert saved.json()["id"].startswith("COM-")


# FR-12 / T10
def test_t10_seeded_repeat_exposes_match_id_and_deterministic_evidence(client):
    """T10: the configured deterministic rule finds the expected seeded complaint."""
    response = client.post(
        "/api/complaints/check-repeat",
        headers=EMP,
        json={"customer_id": "C001", "site_id": "C001-S1", "root_cause": "missed"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["is_repeat"] is True
    assert result["matching_ids"] == ["COM-SEED-1"]
    assert result["count"] == 1
    assert "same customer_id" in result["matches"][0]["reason"]
    assert "same site_id" in result["matches"][0]["reason"]
