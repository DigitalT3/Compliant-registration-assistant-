"""Power BI without Power BI Desktop: write the reporting feed into one Excel workbook that the Power BI service (in the browser) can import.

    python -m scripts.export_powerbi                              # the app must be running; reads REPORTING_TOKEN from .env
    python -m scripts.export_powerbi --url http://127.0.0.1:8001 --out .local/powerbi/feed.xlsx
    python -m scripts.export_powerbi --group customer_service    # only one team's registrations (for a team lead's own copy)

Each reporting table (group_summary, sessions, suggestions, employees, baseline, interviews, ratings) becomes one sheet holding one Excel
table with the same name, which is what Power BI imports. Numbers are written as numbers and times as real date-times, so Power BI
types the columns correctly. Uses only the standard library; it only reads from the app (the same read-only feed Power BI would use).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from backend.services.xlsx import workbook_bytes

DATASETS = ("group_summary", "sessions", "suggestions", "employees", "baseline", "interviews", "ratings")


def _token() -> str:
    if os.environ.get("REPORTING_TOKEN"):
        return os.environ["REPORTING_TOKEN"]
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("REPORTING_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def fetch(url: str, token: str, name: str, group: str | None) -> tuple:
    q = "?format=json" + (f"&group={group}" if group else "")
    req = urllib.request.Request(f"{url.rstrip('/')}/api/reporting/{name}{q}", headers={"X-Reporting-Key": token})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return data["columns"], data["rows"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--out", default=".local/powerbi/renewi_complaints_feed.xlsx")
    ap.add_argument("--group", help="only this user group (customer_service, sales, site_operations)")
    a = ap.parse_args(argv)
    token = _token()
    if not token:
        print("REPORTING_TOKEN is not set (it is in .env). Start the app once so the key exists, or set it in the environment.")
        return 2
    tables = {}
    for name in DATASETS:
        try:
            tables[name] = fetch(a.url, token, name, a.group)
        except urllib.error.HTTPError as e:
            print(f"{name}: the app answered {e.code} ({e.reason}). Is the reporting key the one the running app uses?")
            return 1
        except OSError as e:
            print(f"Cannot reach the app at {a.url} ({e}). Start it first: API_PORT=8001 scripts/run_demo.sh")
            return 1
        print(f"{name:14} {len(tables[name][1]):5} rows")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(workbook_bytes(tables))
    print(f"\nWritten: {out.resolve()}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
