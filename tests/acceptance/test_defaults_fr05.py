"""FR-05: defaults are documented per complaint type and applied when the type is selected."""
import json
from pathlib import Path

from scripts import defaults_doc
from tests.conftest import EMP

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
TYPES = [t["id"] for t in CFG["types"]]
SHOWN = ("channel", "priority", "status", "owner_team", "response_target_days")


def test_the_documentation_is_generated_from_the_configuration_and_up_to_date():
    assert (ROOT / "docs" / "DEFAULTS.md").read_text(encoding="utf-8") == defaults_doc.render(CFG)
    text = (ROOT / "docs" / "DEFAULTS.md").read_text(encoding="utf-8")
    assert all(f"`{t['id']}`" in text and t["en"] in text for t in CFG["types"])


def test_every_type_has_a_complete_set_of_valid_defaults():
    options = CFG["field_options"]
    for t in TYPES:
        d = {**CFG["defaults"]["_all"], **CFG["defaults"][t]}
        assert set(SHOWN) <= set(d), f"{t}: missing {set(SHOWN) - set(d)}"
        assert d["channel"] in options["channel"] and d["priority"] in options["priority"] and d["owner_team"] in options["owner_team"]
        assert int(d["response_target_days"]) > 0


def _prefill(client, ctype, **extra):
    c = client.get("/api/customers/search", params={"q": "100021"}, headers=EMP).json()["candidates"][0]
    return client.post("/api/prefill", headers=EMP, json={"customer_id": c["customer_id"], "complaint_type": ctype, **extra}).json()["fields"]


def test_choosing_each_type_applies_its_documented_defaults(client):
    for t in TYPES:
        f = _prefill(client, t)
        want = {**CFG["defaults"]["_all"], **CFG["defaults"][t]}
        for k in ("priority", "status", "owner_team", "response_target_days"):
            assert f[k] == {"value": want[k], "provenance": "default"}, (t, k)
        assert f["channel"]["value"] == want["channel"]                       # no arrival given: the type's own channel
        assert f["channel"]["provenance"] == "default"


def test_the_arrival_sets_the_channel_over_the_type(client):
    assert _prefill(client, "billing", origin="search")["channel"]["value"] == "phone"
    assert _prefill(client, "service", origin="email")["channel"]["value"] == "email"


def test_what_the_employee_typed_stays_when_the_type_changes(client):
    typed = {"priority": {"value": "high", "provenance": "manual"}, "owner_team": {"value": "sales", "provenance": "edited"}}
    for t in TYPES:
        f = _prefill(client, t, current_fields=typed)
        assert f["priority"]["value"] == "high" and f["owner_team"]["value"] == "sales"
        assert f["response_target_days"]["value"] == CFG["defaults"][t]["response_target_days"]     # the rest still follows the type


def test_the_saved_complaint_carries_the_defaults_of_its_type(client):
    c = client.get("/api/customers/search", params={"q": "100021"}, headers=EMP).json()["candidates"][0]
    for t in TYPES:
        saved = client.post("/api/complaints", headers=EMP, json={"customer_id": c["customer_id"], "channel": "phone", "complaint_type": t,
                                                                "root_cause": "other", "other_reason": "test", "description": "x"}).json()
        rec = client.get(f"/api/complaints/{saved['id']}", headers=EMP).json()
        want = CFG["defaults"][t]
        assert (rec["owner_team"], str(rec["response_target_days"]), rec["priority"]) == (want["owner_team"], want["response_target_days"], want["priority"])
