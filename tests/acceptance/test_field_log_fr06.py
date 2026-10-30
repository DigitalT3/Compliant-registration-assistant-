"""FR-06: the origin of every field (prefilled, default, suggested, typed, edited) is captured in the log."""
from backend import db
from tests.conftest import ADMIN, EMP

TRACKED = ["customer_id", "site_id", "contract_id", "order_id", "container", "channel", "registration_date", "registering_user",
           "priority", "status", "owner_team", "complaint_type", "root_cause", "description", "summary"]


def _register(client):
    sid = client.post("/api/sessions", headers=EMP, json={"mode": "assistant"}).json()["session_id"]
    card = client.get("/api/customers/search", params={"q": "100009"}, headers=EMP).json()["candidates"][0]
    pf = client.post("/api/prefill", headers=EMP, json={"customer_id": card["customer_id"], "origin": "search", "guess_site": True,
                                                         "session_id": sid, "complaint_type": "service"}).json()["fields"]
    client.post(f"/api/sessions/{sid}/events", headers=EMP, json={"type": "field", "field": "channel", "origin": "edited", "changed": True})
    prov = {k: v["provenance"] for k, v in pf.items()}
    prov.update(channel="edited", complaint_type="manual", root_cause="suggested", description="manual", summary="edited")
    saved = client.post("/api/complaints", headers=EMP, json={
        "customer_id": card["customer_id"], "site_id": pf["site_id"]["value"], "contract_id": pf["contract_id"]["value"],
        "order_id": pf["order_id"]["value"], "channel": "email", "complaint_type": "service", "root_cause": "missed",
        "description": "Container not emptied.", "session_id": sid, "field_provenance": prov})
    assert saved.status_code == 201, saved.text
    return sid, saved.json()["id"]


def _log(sid, kind):
    with db.connect() as conn:
        return [tuple(r) for r in conn.execute("SELECT field, origin, changed FROM field_events WHERE session_id=? AND event_type=? ORDER BY id", (sid, kind))]


def test_every_field_is_logged_with_its_origin_when_it_is_filled(client):
    sid, _ = _register(client)
    filled = {f: o for f, o, _ in _log(sid, "field") if _ == 0}
    assert all(filled[f] == "prefilled" for f in ("customer_id", "site_id", "contract_id", "order_id", "container", "registering_user", "registration_date"))
    assert all(filled[f] == "default" for f in ("status", "priority", "channel", "owner_team", "response_target_days"))


def test_a_change_by_the_employee_is_logged_as_changed(client):
    sid, _ = _register(client)
    assert ("channel", "edited", 1) in _log(sid, "field")


def test_the_origin_of_all_fifteen_tracked_fields_is_logged_at_save(client):
    sid, _ = _register(client)
    final = {f: o for f, o, _ in _log(sid, "final")}
    assert sorted(final) == sorted(TRACKED)
    assert (final["channel"], final["complaint_type"], final["description"], final["summary"], final["root_cause"], final["priority"], final["customer_id"]) == \
           ("edited", "manual", "manual", "edited", "suggested", "default", "prefilled")


def test_the_log_can_be_read_without_the_database(client):
    _, cid = _register(client)
    rows = [l.split(",") for l in client.get("/api/export/suggestions.csv", headers=ADMIN).text.splitlines() if l.startswith(cid + ",")]
    by = {r[6]: (r[7], r[8]) for r in rows}
    assert len(rows) == 15 and by["channel"] == ("edited", "changed") and by["description"] == ("manual", "typed") and by["priority"] == ("default", "accepted")
    assert client.get("/api/export/suggestions.csv", headers=EMP).status_code == 403            # employees do not read the log of others
