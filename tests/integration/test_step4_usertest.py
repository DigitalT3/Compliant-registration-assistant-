"""Gap-analysis step 4: everything the timed user test (PRD section 13) needs from the backend."""
import csv
import io

from tests.conftest import ADMIN, EMP

EVAL = {"X-Demo-User": "demo.evaluator"}
LEAD = {"X-Demo-User": "demo.lead"}


def register(client, headers=EMP, mode="assistant", participant="P1", scenario="T01", cause="missed",
             text="Container was not emptied.", **extra):
    s = client.post("/api/sessions", headers=headers, json={"mode": mode, "participant_id": participant,
                                                            "scenario": scenario}).json()["session_id"]
    body = {"customer_id": "C009", "site_id": "C009-S1", "channel": "phone", "complaint_type": "service",
            "root_cause": cause, "description": text, "session_id": s, **extra}
    r = client.post("/api/complaints", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"], s


def summary(client, **params):
    return client.get("/api/analytics/summary", headers=ADMIN, params=params).json()


def test_session_mode_and_participant_are_recorded(client):
    assert client.post("/api/sessions", headers=EMP, json={"mode": "bogus"}).status_code == 422
    r = client.post("/api/sessions", headers=EMP, json={"mode": "plain", "participant_id": " P7 "}).json()
    assert r["mode"] == "plain"
    default = client.post("/api/sessions", headers=EMP, json={}).json()
    assert default["mode"] == "assistant"
    from backend import db
    with db.connect() as conn:
        row = conn.execute("SELECT mode, participant_id FROM sessions WHERE id=?", (r["session_id"],)).fetchone()
    assert (row["mode"], row["participant_id"]) == ("plain", "P7")


def test_dashboard_compares_modes_groups_and_participants(client):
    register(client, mode="assistant", participant="P1")
    register(client, mode="plain", participant="P2", cause="other", other_reason="odd one")
    by_mode = summary(client, group_by="mode")["groups"]
    assert set(by_mode) == {"assistant", "plain"}
    assert by_mode["plain"]["other_share"] == {"value": 1.0, "n": 1}
    assert by_mode["assistant"]["other_share"] == {"value": 0.0, "n": 1}
    assert summary(client, mode="plain")["sessions"]["saved"] == 1
    assert set(summary(client, group_by="group")["groups"]) == {"group_a"}
    assert set(summary(client, group_by="participant")["groups"]) == {"P1", "P2"}
    assert client.get("/api/analytics/summary", headers=ADMIN, params={"group_by": "nope"}).status_code == 422


def test_baseline_needs_evaluate_permission_and_feeds_the_comparison(client):
    row = {"user_group": "group_a", "scenario": "T01", "participant_id": "P1", "seconds": 300}
    assert client.post("/api/baseline", headers=EMP, json=row).status_code == 403
    assert client.post("/api/baseline", headers=EVAL, json=row).status_code == 201
    assert client.post("/api/baseline", headers=EVAL, json={**row, "seconds": 0}).status_code == 422
    client.post("/api/baseline", headers=EVAL, json={**row, "seconds": 500})
    assert client.get("/api/baseline", headers=EVAL).json()["by_group"]["group_a"] == {"mean_seconds": 400.0, "n": 2}
    assert client.get("/api/baseline", headers=LEAD).status_code == 403          # not split by team: not for team leads
    register(client)
    d = summary(client)["duration_seconds"]
    assert d["baseline_seconds"] == 400.0 and d["baseline_n"] == 2 and "stopwatch" in d["baseline_source"]
    assert d["faster_than_baseline"] > 0.99                      # a registration in a test takes well under 1 s
    assert summary(client, group="group_b")["empty"] is True


def test_targets_report_status_and_sample_size(client):
    assert {t["status"] for t in summary(client, group_by="mode").get("targets", [])} <= {"no_data"}   # none yet
    register(client)
    t = {x["id"]: x for x in summary(client)["targets"]}
    assert set(t) == {"time", "other_share", "top3", "prefill", "summary_usable", "cause_accuracy", "daily_use"}
    assert t["time"]["status"] == "met" and t["time"]["indicative"] is True        # n=1 < 10: not a verdict
    assert t["other_share"]["status"] == "met" and t["prefill"]["status"] == "no_data"
    assert t["daily_use"]["status"] == "no_data" and t["cause_accuracy"]["n"] == 0


def test_exit_interviews_drive_the_daily_use_target(client):
    assert client.post("/api/exit-interviews", headers=EMP, json={"participant_id": "P1", "would_use_daily": True}).status_code == 403
    for i in range(6):
        assert client.post("/api/exit-interviews", headers=EVAL,
                           json={"participant_id": f"P{i}", "would_use_daily": i != 5, "comment": "ok"}).status_code == 201
    assert client.get("/api/exit-interviews", headers=EVAL).json()["would_use_daily"] == {"yes": 5, "n": 6}
    assert client.get("/api/exit-interviews", headers=LEAD).status_code == 403
    register(client)
    t = {x["id"]: x for x in summary(client)["targets"]}["daily_use"]
    assert (t["value"], t["n"], t["status"], t["indicative"]) == (5, 6, "met", True)


def test_blind_sample_hides_the_cause_and_is_per_rater(client):
    cid, _ = register(client, text="The lid is broken.", cause="damage")
    items = client.get("/api/evaluations/sample", headers=EVAL).json()["items"]
    assert [i["id"] for i in items] == [cid]                       # seeded history is not part of the sample
    assert set(items[0]) == {"id", "language", "description", "summary"}       # no cause, type or AI output
    assert client.get("/api/evaluations/sample", headers=EMP).status_code == 403
    client.post("/api/evaluations", headers=EVAL, json={"complaint_id": cid, "usable": True, "expert_cause": "damage"})
    assert client.get("/api/evaluations/sample", headers=EVAL).json()["items"] == []
    t = {x["id"]: x for x in summary(client)["targets"]}
    assert t["cause_accuracy"]["value"] == 1.0 and t["summary_usable"]["value"] == 1.0


def test_sessions_csv_export(client):
    _, sid = register(client, participant="=cmd|'/c calc'!A1")     # formula injection attempt in a free-text tag
    r = client.get("/api/export/sessions.csv", headers=LEAD)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:8] == ["session_id", "user", "group", "mode", "participant", "scenario", "status", "duration_s"]
    row = next(x for x in rows[1:] if x[0] == sid)
    assert row[4].startswith("'=") and row[6] == "saved" and float(row[7]) >= 0
    assert "repeat_save_s" in rows[0] and "find_customer_s" in rows[0]
    assert client.get("/api/export/sessions.csv", headers=EMP).status_code == 403
    assert len(list(csv.reader(io.StringIO(client.get("/api/export/sessions.csv", headers=LEAD, params={"mode": "plain"}).text)))) == 1


def test_labels_csv_has_a_blank_label_column_and_no_cause(client):
    cid, _ = register(client, text="=SUM(A1) container broken", cause="damage")
    r = client.get("/api/export/labels-sample.csv", headers=EVAL)
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["complaint_id", "language", "description", "expert_cause"]
    assert rows[1][0] == cid and rows[1][3] == "" and rows[1][2].startswith("'=")
    assert "damage" not in r.text.split("\n", 1)[1].replace("broken", "")
