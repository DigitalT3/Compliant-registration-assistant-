"""Keeps the PoC inside its scope (PRD section 6, docs/SCOPE.md)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NETWORK = re.compile(r"^\s*(import|from)\s+(requests|httpx|urllib\.request|aiohttp|http\.client|smtplib|ftplib|socket)\b", re.M)


def test_no_data_files_are_tracked():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    data = [f for f in files if f.lower().endswith((".csv", ".xlsx", ".xls", ".sqlite3", ".db", ".sqlite"))]
    assert data == [], f"data files must not be committed (real complaint data is out of scope): {data}"


def test_only_the_ai_module_calls_out():
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "backend").rglob("*.py")
                 if p.name != "ai.py" and NETWORK.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"no integration or write-back to other systems: {offenders}"


def test_the_demonstrator_stays_marked_as_synthetic(client):
    assert client.get("/health").json()["synthetic_only"] is True
    assert client.get("/api/config").json()["synthetic_only"] is True
    assert "synthetic data only" in (ROOT / "frontend/src/i18n/en.ts").read_text(encoding="utf-8")
