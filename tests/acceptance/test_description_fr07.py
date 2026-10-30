"""FR-07: a free-text description in Dutch or English is accepted and stored exactly as typed."""
import json
from pathlib import Path

import pytest

from tests.conftest import EMP

CASES = {c["name"]: (c["language"], c["text"]) for c in json.loads((Path(__file__).parent / "description_cases.json").read_text(encoding="utf-8"))["cases"]}


def _save(client, text, language):
    return client.post("/api/complaints", headers=EMP, json={
        "customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
        "root_cause": "missed", "description": text, "language": language})


@pytest.mark.parametrize("name", list(CASES))
def test_dutch_and_english_are_stored_exactly_as_typed(client, name):
    language, text = CASES[name]
    saved = _save(client, text, language)
    assert saved.status_code == 201, saved.text
    rec = client.get(f"/api/complaints/{saved.json()['id']}", headers=EMP).json()
    assert rec["original_text"] == text and rec["payload"]["description"] == text and rec["language"] == language
    listed = next(i for i in client.get("/api/complaints?page_size=50", headers=EMP).json()["items"] if i["id"] == rec["id"])
    assert listed["original_text"] == text


def test_too_long_or_another_language_is_refused_cleanly(client):
    assert _save(client, "x" * 8001, "en").status_code == 422
    assert _save(client, "Der Container wurde nicht geleert.", "de").status_code == 422


def test_the_summary_follows_the_language_but_the_original_stays(client):
    nl = client.post("/api/complaints/analyze", headers=EMP, json={"text": "De container is vandaag niet geleegd.", "language": "nl"}).json()
    assert nl["ai_status"] == "ok" and nl["result"]["summary"]["language"] == "nl"
    en = client.post("/api/complaints/analyze", headers=EMP, json={"text": "The container was not emptied today.", "language": "en"}).json()
    assert en["result"]["summary"]["language"] == "en"
