"""VAL-04: repeat rule against seeded scenarios T10..T20 (pure function + seeded DB)."""
import pytest

from backend import db, seed
from backend.dbutil import connection
from backend.services import complaints
from backend.settings import get_config


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("POC_DB_PATH", str(tmp_path / "r.sqlite3"))
    seed.reset()


def test_seeded_repeat_scenarios(seeded):
    scen = [s for s in seed.load_scenarios() if "repeat_candidate" in s]
    assert len(scen) >= 10
    with connection() as conn:
        for s in scen:
            res = complaints.check_repeat(conn, s["repeat_candidate"])
            exp = s["expected"]
            assert res["is_repeat"] is exp["repeat"], s["id"]
            assert [m["id"] for m in res["matches"]] == sorted(exp["matches"], reverse=True) or \
                sorted(m["id"] for m in res["matches"]) == sorted(exp["matches"]), s["id"]
            assert res["missing_fields"] == exp.get("missing_fields", [])
            assert res["rule_version"] == get_config()["repeat_rule"]["version"]
