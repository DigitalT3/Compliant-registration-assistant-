"""FR-07: a free-text description in Dutch or English is accepted and stored exactly as typed."""
import pytest

from tests.conftest import EMP

CASES = {
    "nl plain": ("nl", "De container bij onze locatie is vandaag niet geleegd. Dit is de derde keer deze maand."),
    "nl accents": ("nl", "Café 'De Ruiter' – ëïü é è, €45,50 te veel gefactureerd; ½ container, 10% korting \"beloofd\"."),
    "en plain": ("en", "The container at our depot was not emptied on Tuesday. It was missed again."),
    "en quotes": ("en", "Driver said \"it's not my job\" & left; invoice #1234 <b>wrong</b>; SQL: '; DROP TABLE complaints;--"),
    "spaces": ("en", "  leading spaces, double  inner  spaces, trailing spaces and tab\t  "),
    "newlines": ("nl", "Regel 1\r\nRegel 2\n\nRegel 4 na lege regel\n"),
    "emoji": ("en", "Bin overflowing 😡 – smells terrible 🤢 ü"),
    "longest": ("nl", ("Dit is een lange klacht. " * 400)[:8000]),
}


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
