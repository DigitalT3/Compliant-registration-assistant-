"""Smoke-test the configured AI provider against sample complaints (needs AI_PROVIDER=live).

    AI_PROVIDER=live AI_BASE_URL=https://<eu-endpoint>/v1 AI_API_KEY=... AI_MODEL=... \
        python -m scripts.live_ai_check

Sends only the fictional sample texts below. Prints latency, the suggested cause and whether it
matches the expected one. Exits non-zero if the provider is not live or any call fails, so it can
gate the demo. It does not replace the expert-labelled accuracy test in the PRD (>= 85%).
"""
import sys
import time

from backend import settings
from backend.services import ai

SAMPLES = [
    ("en", "Our container was not emptied on Tuesday, the collection never happened.", "missed"),
    ("nl", "Onze container is vandaag niet geleegd, de inzameling is gemist.", "missed"),
    ("en", "The lid of the container is broken and it no longer closes.", "damage"),
    ("en", "We were charged twice on the latest invoice, please correct it.", "invoice"),
    ("nl", "De chauffeur was onbeleefd tegen onze medewerkers.", "conduct"),
    ("en", "We still have not received the recycling certificate for last quarter.", "other"),
]


def main() -> int:
    cfg = settings.get_config()
    if settings.ai_settings()["provider"] == "mock":
        print("The AI provider is the mock (set LLM_PROVIDER=bedrock or AI_PROVIDER=live); nothing to check.")
        return 2
    provider, failures, hits = ai.get_provider(), 0, 0
    payload = {"taxonomy": cfg["root_causes"], "types": [t["id"] for t in cfg["types"]],
               "template_extras_by_type": cfg["summary"]["by_type"], "site_name": None, "complaint_type": None}
    for lang, text, expected in SAMPLES:
        start = time.monotonic()
        try:
            out = ai.MODELS["analyze"].model_validate(provider.complete_json("analyze", {**payload, "text": text, "language": lang}))
        except Exception as e:  # noqa: BLE001 - report every failure kind
            failures += 1
            print(f"FAIL  {text[:50]!r}: {type(e).__name__} {e}")
            continue
        ms = int((time.monotonic() - start) * 1000)
        top = out.classification.candidates[0].root_cause_id if out.classification.candidates else None
        hits += top == expected
        print(f"{'ok  ' if top == expected else 'diff'}  {ms:5d} ms  expected={expected:8s} got={top}  | {out.summary.what}")
    print(f"\n{len(SAMPLES) - failures}/{len(SAMPLES)} calls valid, {hits} matched the expected cause.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
