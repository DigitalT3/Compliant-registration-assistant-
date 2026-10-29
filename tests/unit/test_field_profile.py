"""Field profile script: fill-rate and value spread per field, default candidates, privacy of free text."""
import csv

import pytest

from scripts import field_profile as fp


def rows_of(n_phone=9, n_email=1, **extra):
    out = [{"created": f"2026-0{1 + i % 9}-15", "channel": "phone", "priority": "normal", "note": f"call {i}"} for i in range(n_phone)]
    out += [{"created": "2026-02-01", "channel": "Email ", "priority": "high", "note": "x"} for _ in range(n_email)]
    return [{**r, **extra} for r in out]


def by_field(table):
    return {t["field"]: t for t in table}


def test_fill_rate_distinct_top_value_and_default_candidate():
    rows = rows_of(n_phone=18, n_email=2)                       # 90 % phone
    rows[0]["priority"] = "N/A"                                  # placeholders count as empty
    rows[1]["priority"] = "  "
    t = by_field(fp.profile(rows, ["channel", "priority"], threshold=0.8))
    assert t["channel"]["filled"] == 20 and t["channel"]["fill_rate"] == 1.0
    assert (t["channel"]["top_value"], t["channel"]["top_count"], t["channel"]["top_share"]) == ("phone", 18, 0.9)
    assert t["channel"]["flag"] == "default candidate" and t["channel"]["distinct"] == 2
    assert t["priority"]["filled"] == 18 and t["priority"]["fill_rate"] == 0.9


def test_values_are_grouped_regardless_of_case_and_spaces():
    rows = [{"channel": v} for v in ["Phone", "phone", " PHONE ", "email"] * 5]
    t = by_field(fp.profile(rows, ["channel"]))["channel"]
    assert t["distinct"] == 2 and t["top_count"] == 15 and t["top_share"] == 0.75 and t["flag"] == ""     # below 80 %


def test_threshold_and_minimum_records():
    rows = rows_of(n_phone=15, n_email=5)                        # 75 %
    assert by_field(fp.profile(rows, ["channel"], threshold=0.7))["channel"]["flag"] == "default candidate"
    assert by_field(fp.profile(rows, ["channel"], threshold=0.8))["channel"]["flag"] == ""
    assert by_field(fp.profile(rows[:4], ["channel"], min_n=10))["channel"]["flag"] == "too few records"
    assert by_field(fp.profile([{"channel": ""}], ["channel"]))["channel"]["flag"] == "empty"


def test_free_text_and_identifiers_never_show_their_values():
    rows = [{"description": "Mevrouw Jansen belde", "order_id": f"ORD-{i}", "channel": "phone",
             "remark": "x" * 50, "city": "Utrecht"} for i in range(30)]
    t = by_field(fp.profile(rows, ["description", "order_id", "remark", "city"]))
    assert t["description"]["flag"] == "free text" and t["description"]["top_value"] == "(hidden)"      # by column name
    assert t["remark"]["top_value"] == "(hidden)"
    assert t["order_id"]["flag"] == "varied" and t["order_id"]["top_value"] == "(varied)"             # too many distinct values
    assert t["city"]["flag"] == "default candidate" and t["city"]["top_value"] == "Utrecht"
    text = fp.render(fp.profile(rows, ["description", "order_id"]))
    assert "Jansen" not in text and "ORD-1" not in text


def test_window_keeps_the_last_months_and_reports_short_coverage():
    rows = [{"created": d, "channel": "phone"} for d in ["2025-01-10", "2025-12-31", "2026-03-01", "2026-05-31", "not a date"]]
    kept, info = fp.window(rows, "created", 4)                  # four months back from the newest record (31 May)
    assert [r["created"] for r in kept] == ["2026-03-01", "2026-05-31"] and info["unreadable_dates"] == 1
    kept, info = fp.window(rows, "created", None)
    assert len(kept) == 4 and info["covered_months"] > 16
    assert fp.window(rows, None, 4)[0] == rows                                                         # no date column: no window
    assert fp.parse_date("31-12-2025").year == 2025 and fp.parse_date("2026-05-31T10:00:00Z").month == 5
    assert fp.parse_date("garbage") is None


def test_reads_comma_and_semicolon_exports(tmp_path):
    for delimiter in (",", ";"):
        path = tmp_path / f"export{ord(delimiter)}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=delimiter)
            w.writerow(["created", "channel"])
            w.writerows([["2026-01-01", "phone"]] * 12)
        header, rows = fp.read_csv(str(path))
        assert header == ["created", "channel"] and len(rows) == 12
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(SystemExit):
        fp.read_csv(str(empty))


def test_command_line_prints_candidates_and_writes_the_table(tmp_path, capsys):
    src, out = tmp_path / "in.csv", tmp_path / "profile.csv"
    with open(src, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["created", "channel", "priority"])
        w.writerows([["2026-01-01", "phone", "normal"]] * 18 + [["2026-02-01", "email", "high"]] * 2)
    assert fp.main(["--csv", str(src), "--date-column", "created", "--months", "12", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "20 records" in text and "Default candidates" in text and "channel, priority" in text
    assert "WARNING: the data covers" in text                                                           # 1 month of data, 12 asked for
    written = list(csv.DictReader(open(out)))
    assert {r["field"] for r in written} == {"channel", "priority"} and written[0]["top_share"] == "0.9"
    with pytest.raises(SystemExit):
        fp.main(["--csv", str(src), "--fields", "nope"])                                                  # unknown column is explained
    with pytest.raises(SystemExit):
        fp.main(["--csv", str(src), "--months", "6"])                                                     # months needs a date column


def test_profiles_the_poc_database(client, capsys):
    from tests.integration.test_step4_usertest import register
    from tests.conftest import EMP
    register(client, headers=EMP)
    header, rows = fp.read_poc("all")
    assert header[0] == "created" and "channel" in header and "description" not in header                # free text is never read
    assert len(rows) >= 16
    only_poc = fp.read_poc("poc")[1]
    assert len(only_poc) == 1 and len(fp.read_poc("seed")[1]) == len(rows) - 1
    assert fp.main(["--poc", "--source", "all"]) == 0
    assert "Field profile: PoC complaints (all)" in capsys.readouterr().out
