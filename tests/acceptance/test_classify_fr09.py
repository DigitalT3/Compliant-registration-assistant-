"""FR-09: the complaint type and the top three root causes from the list, each with a one-line reason; top-3 acceptance is measured."""
import json
from pathlib import Path

from backend.settings import get_config
from scripts.classify_eval import structure_problems
from tests.conftest import ADMIN, EMP

CASES = json.loads((Path(__file__).parent / "summary_cases.json").read_text(encoding="utf-8"))["cases"]


def _lists():
    cfg = get_config()
    return {c["id"] for c in cfg["root_causes"]}, {t["id"] for t in cfg["types"]}


def test_type_and_up_to_three_listed_causes_with_a_one_line_reason(client):
    """With the keyword mock (the live model is checked by scripts/classify_eval.py): whatever is suggested is well-formed."""
    causes, types = _lists()
    answered = 0
    for case in CASES:
        out = client.post("/api/complaints/classify", headers=EMP, json={"text": case["text"]}).json()
        assert out["ai_status"] == "ok", case["id"]
        assert out["taxonomy_version"]                                              # which list the suggestion came from
        if out["result"]["candidates"]:                                             # the mock only knows some keywords
            answered += 1
            assert structure_problems(out["result"], causes, types, need=None) == [], case["id"]
    assert answered >= 6


def test_nothing_is_preselected_when_the_assistant_is_unsure(client):
    out = client.post("/api/complaints/classify", headers=EMP, json={"text": "Something odd happened but I am not sure what."}).json()
    assert out["low_confidence"] is True and out["preselect"] is None


def _register(client, text, chosen):
    """One registration in its own session, saving ``chosen`` (an index into the suggestions, or a cause id)."""
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    shown = client.post("/api/complaints/classify", headers=EMP, json={"text": text, "session_id": sid}).json()["result"]["candidates"]
    cause = shown[chosen]["root_cause_id"] if isinstance(chosen, int) else chosen
    r = client.post("/api/complaints", headers=EMP, json={"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
                                                          "root_cause": cause, "other_reason": "test reason" if cause == "other" else None, "description": text, "session_id": sid})
    assert r.status_code == 201, r.text
    return [c["root_cause_id"] for c in shown], cause


def test_top3_acceptance_is_measured_from_what_was_shown_and_what_was_saved(client):
    text = "The container at our depot was not emptied on Tuesday, it was missed again."
    _register(client, text, 0)                                                        # kept the first suggestion
    shown, cause = _register(client, text, "weighing")                                # a cause that was not suggested
    assert "weighing" not in shown
    top3 = client.get("/api/analytics/summary", headers=ADMIN).json()["classification"]["top_three_rate"]
    assert (top3["value"], top3["n"]) == (0.5, 2)
    row = next(t for t in client.get("/api/analytics/summary", headers=ADMIN).json()["targets"] if t["id"] == "top3")
    assert row["n"] == 2 and row["status"] == "not_met"                              # target: 70% accepted within the top three
