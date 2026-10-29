"""FR-02 check against the configured model: do the ten typical e-mails (tests/acceptance/email_cases.json) find the right customer?

    python -m scripts.email_eval            # uses the AI provider and database the app is configured for
    LLM_PROVIDER=mock python -m scripts.email_eval

Reads synthetic e-mails only. Writes nothing except the usual AI-call log rows.
"""
import json
import sys
from pathlib import Path

from backend import db
from backend.routers.complaints import ExtractIn, extract
from backend.services import lookup

CASES = Path(__file__).resolve().parents[1] / "tests" / "acceptance" / "email_cases.json"


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    right = 0
    with db.connect() as conn:
        for k in cases:
            out = extract(ExtractIn(text=k["text"]), {"id": None})
            r = out.get("result") or {}
            q = r.get("customer_query")
            found = lookup.search(conn, q) if q else None
            number = found["candidates"][0]["number"] if found and found["count"] == 1 else None
            right += number == k["expected"]
            print(f"{k['id']}  expected {k['expected']}  found {number}  by {r.get('matched_by')}  ai={out['ai_status']}")
    print(f"correct {right} of {len(cases)}  (criterion: at least 8)")
    return 0 if right >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
