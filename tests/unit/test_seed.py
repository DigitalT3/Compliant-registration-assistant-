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
    assert first["user_version"] == 2


def test_dataset_minimums(fresh_db):
    c = seed.fingerprint()["counts"]
    assert c["customers"] >= 20
    assert c["complaints"] >= 15
    assert len(seed.load_scenarios()) >= 10
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM complaints WHERE is_seed=1").fetchone()[0] == c["complaints"]


def test_seed_if_empty_does_not_duplicate(fresh_db):
    assert seed.seed_if_empty() is False
