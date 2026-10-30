"""FR-17: the dashboard shows time per registration, the "Other" share, suggestion acceptance and the repeat rate, by user group.

Five registrations in three user groups are made with known outcomes (and known times, written straight into the log), so the
expected numbers below are worked out by hand, not by the dashboard's own code.
"""
from datetime import datetime, timedelta

import pytest

from backend import db
from backend.services import sessions as sessions_svc
from tests.conftest import ADMIN, EMP
from tests.integration.test_team_scope import signed_in

TEXT = "De container is niet geleegd en de chauffeur was te laat en onbeleefd."          # the mock suggests late, missed, conduct
T0 = datetime.fromisoformat("2026-10-28T09:00:00+00:00")


def _time(sid, visits):
    """Write the log the way a registration with these visits (step, seconds) would have left it."""
    with db.connect() as conn:
        conn.execute("DELETE FROM step_events WHERE session_id=?", (sid,))
        t = T0
        for step, seconds in visits:
            conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)", (sid, step, "step_entered", t.isoformat()))
            t += timedelta(seconds=seconds)
            conn.execute("INSERT INTO step_events(session_id,step,event_type,at) VALUES(?,?,?,?)", (sid, step, "step_completed", t.isoformat()))
        conn.execute("UPDATE sessions SET started=?, ended=? WHERE id=?", (T0.isoformat(), t.isoformat(), sid))
        conn.commit()


def _register(client, headers, customer, site, pick, summary="kept", times=(10, 10, 10, 10, 10)):
    """pick: index into the suggested causes, or a cause id outside them."""
    sid = client.post("/api/sessions", headers=headers, json={"mode": "assistant"}).json()["session_id"]
    shown = client.post("/api/complaints/classify", headers=headers, json={"text": TEXT, "session_id": sid}).json()["result"]["candidates"]
    ids = [c["root_cause_id"] for c in shown]
    assert len(ids) == 3
    cause = ids[pick] if isinstance(pick, int) else pick
    prov = {"root_cause": "suggested" if pick == 0 else "edited", "summary": "suggested" if summary == "kept" else "edited", "complaint_type": "suggested"}
    r = client.post("/api/complaints", headers=headers, json={
        "customer_id": customer, "site_id": site, "channel": "phone", "complaint_type": "service", "root_cause": cause,
        "other_reason": "Seagull nest" if cause == "other" else None, "description": TEXT, "session_id": sid, "field_provenance": prov})
    assert r.status_code == 201, r.text
    _time(sid, list(zip(sessions_svc.STEPS, times)))
    return r.json()


@pytest.fixture
def three_groups(client):
    cs = signed_in(client, "cs@example.nl", "customer_service")
    sales = signed_in(client, "sales@example.nl", "sales")
    ops = signed_in(client, "ops@example.nl", "site_operations")
    _register(client, cs, "C005", "C005-S1", 0)                                                   # kept first cause, summary kept        50 s
    two = _register(client, cs, "C001", "C001-S1", 1, summary="edited", times=(10, 10, 20, 30, 10))   # another of the three, a repeat, summary edited  80 s
    _register(client, sales, "C008", "C008-S1", "other", summary="edited", times=(5, 5, 5, 5, 5))    # outside the suggestions: Other       25 s
    _register(client, sales, "C011", "C011-S1", 0, times=(10, 10, 10, 5, 5))                          # kept                                  40 s
    _register(client, ops, "C012", "C012-S1", 0, times=(900, 10, 10, 10, 10))                          # first step left open 15 minutes      640 s (cap 600)
    sid = client.post("/api/sessions", headers=ops, json={"mode": "assistant"}).json()["session_id"]  # a registration that was started and given up
    client.post(f"/api/sessions/{sid}/complete", headers=ops, json={"outcome": "abandoned"})
    return two


def _by_group(client):
    out = client.get("/api/analytics/summary", headers=ADMIN, params={"group_by": "group"}).json()
    return out, out["groups"]


def test_time_per_registration_overall_and_by_group(client, three_groups):
    out, g = _by_group(client)
    d = out["duration_seconds"]
    assert (d["n"], d["mean"], d["median"]) == (5, 167.0, 50.0)                                   # (50+80+25+40+640)/5; the 940 s wall clock is capped at 640
    assert (g["customer_service"]["mean_duration"], g["customer_service"]["n_duration"]) == (65.0, 2)
    assert (g["sales"]["mean_duration"], g["sales"]["n_duration"]) == (32.5, 2)
    assert (g["site_operations"]["mean_duration"], g["site_operations"]["n_duration"]) == (640.0, 1)   # the abandoned one has no time
    assert out["sessions"]["started"] == 6 and out["sessions"]["saved"] == 5 and out["sessions"]["abandoned"] == 1


def test_other_share_overall_and_by_group(client, three_groups):
    out, g = _by_group(client)
    assert (out["classification"]["other_share"]["value"], out["classification"]["other_share"]["n"]) == (0.2, 5)
    assert g["sales"]["other_share"] == {"value": 0.5, "n": 2} and g["customer_service"]["other_share"]["value"] == 0.0 and g["site_operations"]["other_share"]["value"] == 0.0


def test_repeat_rate_overall_and_by_group(client, three_groups):
    out, g = _by_group(client)
    assert out["repeat"]["rate"] == {"value": 0.2, "n": 5}
    assert g["customer_service"]["repeat_rate"] == {"value": 0.5, "n": 2} and g["sales"]["repeat_rate"]["value"] == 0.0


def test_suggestion_acceptance_overall_and_by_group(client, three_groups):
    out, g = _by_group(client)
    a = out["acceptance"]
    assert a["cause_first"] == {"value": 0.6, "n": 5}                                             # CS1, S2 and O1 kept the first suggestion
    assert a["top3"] == {"value": 0.8, "n": 5}                                                    # all but the "Other" were among the three shown
    assert a["summary_kept"] == {"value": 0.6, "n": 5} and a["type_kept"] == {"value": 1.0, "n": 5}
    assert g["customer_service"]["acceptance"]["cause_first"] == {"value": 0.5, "n": 2}
    assert g["customer_service"]["acceptance"]["top3"] == {"value": 1.0, "n": 2}                  # the changed one was still within the three
    assert g["sales"]["acceptance"]["cause_first"] == {"value": 0.5, "n": 2} and g["sales"]["acceptance"]["top3"] == {"value": 0.5, "n": 2}
    assert g["site_operations"]["acceptance"]["cause_first"] == {"value": 1.0, "n": 1}
    assert g["sales"]["acceptance"]["summary_kept"] == {"value": 0.5, "n": 2}


def test_the_dashboard_time_equals_the_time_in_the_audit_trail_and_the_csv(client, three_groups):
    one = _by_group(client)[0]["duration_seconds"]
    items = client.get("/api/audit/records", headers=ADMIN, params={"include_seed": "false", "page_size": 50}).json()["items"]
    totals = sorted(client.get(f"/api/audit/records/{i['id']}", headers=ADMIN).json()["log"]["total_seconds"] for i in items)
    assert totals == [25.0, 40.0, 50.0, 80.0, 640.0] and round(sum(totals) / len(totals), 2) == one["mean"]
    rows = client.get("/api/export/sessions.csv", headers=ADMIN).text.splitlines()
    durations = sorted(float(r.split(",")[7]) for r in rows[1:] if r.split(",")[6] == "saved")
    assert durations == totals                                                                    # the export says the same


def test_group_names_are_published_for_the_screen(client):
    assert [f["id"] for f in client.get("/api/config").json()["functions"]] == ["customer_service", "sales", "site_operations"]
