"""The Power BI feed (FR-17): read-only tables for the dashboard measures, behind a reporting key or an analytics sign-in."""
import csv
import io

from tests.conftest import ADMIN, EMP
from tests.integration.test_team_scope import PROV, register, signed_in

KEY = {"X-Reporting-Key": "test-reporting-key"}


def rows(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def test_the_key_must_be_set_and_right(client, monkeypatch):
    monkeypatch.delenv("REPORTING_TOKEN", raising=False)
    assert client.get("/api/reporting/group_summary", headers=KEY).status_code == 401           # no key configured: nothing opens it
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    assert client.get("/api/reporting/group_summary", headers={"X-Reporting-Key": "wrong"}).status_code == 401
    assert client.get("/api/reporting/group_summary", headers=KEY).status_code == 200
    assert client.get("/api/reporting/group_summary").status_code == 401                         # no key, no sign-in
    assert client.get("/api/reporting/group_summary", headers=EMP).status_code == 403           # an employee has no analytics permission


def test_group_summary_has_the_fr17_measures_by_group(client, monkeypatch):
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    service = signed_in(client, "karel.service@example.nl", "customer_service")
    register(client, headers=sales, participant="S1", field_provenance=PROV)
    register(client, headers=service, participant="C1", field_provenance=PROV)
    table = rows(client.get("/api/reporting/group_summary", headers=KEY))
    head = table[0]
    body = {r[0]: dict(zip(head, r)) for r in table[1:]}
    for col in ("mean_duration_s", "other_share", "repeat_rate", "first_cause_kept", "top3_accepted", "summary_kept", "type_kept", "other_share_n"):
        assert col in head, col
    assert {"All groups", "sales", "customer_service"} <= set(body)
    assert body["sales"]["sessions"] == "1" and body["All groups"]["sessions"] == "2"
    as_json = client.get("/api/reporting/group_summary", headers=KEY, params={"format": "json"}).json()
    assert as_json["dataset"] == "group_summary" and as_json["columns"] == head


def test_a_lead_sees_their_team_only_and_not_the_user_test_tables(client):
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    service = signed_in(client, "karel.service@example.nl", "customer_service")
    lead = signed_in(client, "lotte.lead@example.nl", "sales", role="lead")
    register(client, headers=sales, participant="S1")
    register(client, headers=service, participant="C1")
    sessions = rows(client.get("/api/reporting/sessions", headers=lead))
    assert {r[sessions[0].index("group")] for r in sessions[1:]} == {"sales"}
    assert client.get("/api/reporting/baseline", headers=lead).status_code == 403
    assert client.get("/api/reporting/baseline", headers=ADMIN).status_code == 200


def test_every_dataset_reads_and_unknown_ones_do_not(client, monkeypatch):
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    for name in ("group_summary", "sessions", "suggestions", "employees", "baseline", "interviews", "ratings"):
        assert client.get(f"/api/reporting/{name}", headers=KEY).status_code == 200, name
    assert client.get("/api/reporting/users", headers=KEY).status_code == 404
    assert client.post("/api/reporting/sessions", headers=KEY, json={}).status_code == 405       # read-only


def test_a_read_is_audited(client, monkeypatch):
    from backend import db
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    client.get("/api/reporting/sessions", headers=KEY)
    conn = db.connect()
    try:
        assert conn.execute("SELECT count(*) FROM audit WHERE action='reporting_read' AND actor='reporting-key'").fetchone()[0] == 1
    finally:
        conn.close()


def test_the_workbook_has_one_excel_table_per_reporting_table(client, monkeypatch):
    import xml.etree.ElementTree as ET
    import zipfile
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    register(client, headers=sales, participant="S1", field_provenance=PROV)
    assert client.get("/api/reporting/workbook.xlsx").status_code == 401
    assert client.get("/api/reporting/workbook.xlsx", headers=EMP).status_code == 403
    r = client.get("/api/reporting/workbook.xlsx", headers=KEY)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", ns)]
    assert sheets == ["group_summary", "sessions", "suggestions", "employees", "baseline", "interviews", "ratings"]
    tables = {ET.fromstring(z.read(n)).get("name"): ET.fromstring(z.read(n)) for n in z.namelist() if n.startswith("xl/tables/")}
    assert set(tables) == set(sheets)
    sess = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
    head = [c.find("m:is/m:t", ns).text for c in sess.find("m:sheetData", ns)[0]]
    assert "duration_s" in head and "group" in head
    assert [c.get("name") for c in tables["sessions"].findall("m:tableColumns/m:tableColumn", ns)] == head       # the table's columns are the header row
    assert len(list(sess.find("m:sheetData", ns))) >= 2                                                          # header and the registration
    lead = signed_in(client, "lena.lead@example.nl", "sales", role="lead")
    z2 = zipfile.ZipFile(io.BytesIO(client.get("/api/reporting/workbook.xlsx", headers=lead).content))
    assert [s.get("name") for s in ET.fromstring(z2.read("xl/workbook.xml")).findall("m:sheets/m:sheet", ns)] == ["group_summary", "sessions", "suggestions", "employees"]


def test_the_workbook_writer_types_numbers_and_times():
    import xml.etree.ElementTree as ET
    import zipfile
    from backend.services.xlsx import workbook_bytes
    z = zipfile.ZipFile(io.BytesIO(workbook_bytes({"t": (["name", "seconds", "recorded_at"], [["a & <b>", 85.5, "2026-10-30T16:27:40+00:00"], [None, 3, None]])})))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows_ = ET.fromstring(z.read("xl/worksheets/sheet1.xml")).find("m:sheetData", ns)
    first = {c.get("r"): c for c in rows_[1]}
    assert first["A2"].find("m:is/m:t", ns).text == "a & <b>"                                                     # text is escaped and kept as text
    assert first["B2"].get("t") is None and first["B2"].find("m:v", ns).text == "85.5"                            # a number stays a number
    assert first["C2"].get("s") == "1" and float(first["C2"].find("m:v", ns).text) > 46000                        # a time is a real date-time
    assert {c.get("r") for c in rows_[2]} == {"B3"}                                                              # empty cells are left out


def test_the_dashboard_gets_the_report_link_only_when_it_is_an_https_link(client, monkeypatch):
    monkeypatch.delenv("POWERBI_REPORT_URL", raising=False)
    assert client.get("/api/config").json()["powerbi_report_url"] == ""
    monkeypatch.setenv("POWERBI_REPORT_URL", "javascript:alert(1)")
    assert client.get("/api/config").json()["powerbi_report_url"] == ""                                          # nothing but https is passed on
    monkeypatch.setenv("POWERBI_REPORT_URL", "https://app.powerbi.com/groups/me/reports/abc")
    assert client.get("/api/config").json()["powerbi_report_url"] == "https://app.powerbi.com/groups/me/reports/abc"


def test_the_feed_shows_the_person_s_name_not_their_id(client, monkeypatch):
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    register(client, headers=sales, participant="S1", field_provenance=PROV)
    for name in ("sessions", "suggestions"):
        table = rows(client.get(f"/api/reporting/{name}", headers=KEY))
        users = {r[table[0].index("user")] for r in table[1:]}
        assert users == {"Test Sanne.Sales"}, (name, users)
    wb = client.get("/api/reporting/workbook.xlsx", headers=KEY)
    assert wb.status_code == 200 and b"Test Sanne.Sales" in __import__("zipfile").ZipFile(io.BytesIO(wb.content)).read("xl/worksheets/sheet2.xml")


def test_the_feed_has_a_start_time_and_can_be_limited_to_registrations_since_a_time(client, monkeypatch):
    monkeypatch.setenv("REPORTING_TOKEN", "test-reporting-key")
    sales = signed_in(client, "sanne.sales@example.nl", "sales")
    register(client, headers=sales, participant="S1", field_provenance=PROV)
    table = rows(client.get("/api/reporting/sessions", headers=KEY))
    assert "started" in table[0] and table[1][table[0].index("started")].startswith("20")             # a time, so a report can filter by it
    for name in ("sessions", "suggestions", "group_summary", "employees"):
        everything = rows(client.get(f"/api/reporting/{name}", headers=KEY))
        later = rows(client.get(f"/api/reporting/{name}", headers=KEY, params={"date_from": "2999-01-01T00:00:00+00:00"}))
        assert len(everything) > 1 and len(later) <= 1, name                                          # nothing started that late: only a header, or nothing
    assert len(rows(client.get("/api/reporting/sessions", headers=KEY, params={"date_from": "2000-01-01T00:00:00+00:00"}))) == len(table)
    assert client.get("/api/analytics/summary", headers=ADMIN, params={"date_from": "2999-01-01T00:00:00+00:00"}).json()["empty"] is True


def test_a_workbook_session_start_is_a_real_date_time():
    import zipfile
    from backend.services.xlsx import workbook_bytes
    z = zipfile.ZipFile(io.BytesIO(workbook_bytes({"t": (["session_id", "started"], [["a", "2026-10-30T16:27:40.123456+00:00"]])})))
    assert b's="1"' in z.read("xl/worksheets/sheet1.xml")                                              # the time column gets the date-time style
