"""FR-02: a pasted e-mail finds the right customer for at least 8 of 10 typical complaints (PRD acceptance criterion)."""
import json
from pathlib import Path

from tests.conftest import EMP

CASES = json.loads((Path(__file__).parent / "email_cases.json").read_text(encoding="utf-8"))["cases"]


def customer_for(client, text):
    """What the screen does: extract, then search with the query the server chose."""
    r = client.post("/api/complaints/extract", headers=EMP, json={"text": text}).json()["result"]
    if not r["customer_query"]:
        return None, r
    found = client.get("/api/customers/search", headers=EMP, params={"q": r["customer_query"]}).json()
    return (found["candidates"][0]["number"] if found["count"] == 1 else None), r


def test_ten_typical_emails_find_the_right_customer(client):
    right = [k["id"] for k in CASES if customer_for(client, k["text"])[0] == k["expected"]]
    assert len(CASES) == 10 and len(right) >= 8, f"only {len(right)} of 10 found: {right}"
    assert len(right) == 10                                    # with the mock provider every one of them is expected to pass


def test_the_text_is_kept_and_headers_are_dropped(client):
    _, r = customer_for(client, CASES[0]["text"])
    assert "niet geleegd" in r["description"] and "Onderwerp" not in r["description"]


def test_a_number_that_exists_wins_over_a_name(client):
    text = "Klantnummer 100009. Wij zijn Zorgcentrum Het Anker, maar mailen namens Boerenhof Kaasmakerij VOF."
    number, r = customer_for(client, text)
    assert number == "100009" and r["matched_by"] == "customer_number"


def test_unknown_companies_and_short_words_do_not_match(client):
    for text in ("Dear team, our container was not emptied. Regards, a customer of yours.",
                 "Hallo, mijn buurman klaagt over het afval. Groet, Piet van de Wasserij"):
        assert customer_for(client, text)[0] is None


def test_a_wrong_number_does_not_hide_the_company_name(client):
    number, r = customer_for(client, "Klant 100999 (typfout). Met vriendelijke groet, Brouwer Transport")
    assert number == "100010" and r["matched_by"] == "name"
