"""VAL-01: seed is reproducible and meets dataset minimums."""
import pytest

from backend import db, seed


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("POC_DB_PATH", str(tmp_path / "t.sqlite3"))
    seed.reset()
    return tmp_path


def test_reset_is_deterministic(fresh_db):
    first = seed.fingerprint()
    seed.reset()
    assert seed.fingerprint() == first
    assert first["user_version"] == 12


def test_dataset_minimums(fresh_db):
    c = seed.fingerprint()["counts"]
    assert c["customers"] >= 20
    assert c["complaints"] >= 40
    assert len(seed.load_scenarios()) >= 10
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM complaints WHERE is_seed=1").fetchone()[0] == c["complaints"]


def test_seed_if_empty_does_not_duplicate(fresh_db):
    assert seed.seed_if_empty() is False


def test_reset_refuses_the_live_postgres_schema(monkeypatch):
    import pytest
    monkeypatch.setenv("POC_DB", "postgres")
    monkeypatch.delenv("POC_PG_SCHEMA", raising=False)
    monkeypatch.delenv("POC_ALLOW_LIVE_RESET", raising=False)
    with pytest.raises(RuntimeError, match="Refusing to reset the live Postgres schema"):
        seed.reset()


def test_reanchor_moves_the_dates_by_whole_days_and_back(fresh_db):
    from datetime import timedelta
    from backend import db

    def snapshot():
        with db.connect() as conn:
            return {"created": [r["created"] for r in conn.execute("SELECT created FROM complaints ORDER BY id").fetchall()],
                    "orders": [r["date"] for r in conn.execute("SELECT date FROM orders ORDER BY id").fetchall()],
                    "valid_to": [r["valid_to"] for r in conn.execute("SELECT valid_to FROM contracts ORDER BY id").fetchall()],
                    "counts": {k: v for k, v in seed.fingerprint()["counts"].items() if k != "app_settings"}}      # the remembered anchor is one setting row
    before, anchor = snapshot(), db.seed_anchor()
    assert seed.reanchor(anchor) == 0                                       # already there: nothing moves
    assert seed.reanchor(anchor + timedelta(days=5, hours=3)) == 5          # whole days only, the time of day stays
    after = snapshot()
    assert after["counts"]["complaints"] == before["counts"]["complaints"]
    assert after["created"][0] == (db.parse_dt(before["created"][0]) if hasattr(db, "parse_dt") else __import__("datetime").datetime.fromisoformat(before["created"][0]) + timedelta(days=5)).isoformat()
    assert after["valid_to"][0] == (__import__("datetime").date.fromisoformat(before["valid_to"][0]) + timedelta(days=5)).isoformat()
    assert seed.reanchor(anchor + timedelta(days=5, hours=9)) == 0          # the same day again: nothing moves
    assert seed.reanchor(anchor) == -5 and snapshot() == before             # and back, exactly
