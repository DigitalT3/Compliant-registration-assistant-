# Known Issues and Handover Limitations

## Incomplete or unverified items

Live AI mode requires approved credentials and has not been tested. The deterministic mock provider demonstrates integration and fallback behaviour only; it is not evidence of summary quality, classification accuracy, calibrated confidence, or real-world performance.

The PoC uses a provisional taxonomy, field mapping, required-field set, defaults, and repeat rule. The dashboard calculates from recorded PoC events, but no real-user sessions, current-process baseline, or validated time-saving result exists. FR-18 through FR-20 (beyond the synthetic labelling tool) remain later-phase work because no approved historical dataset or expert-labelled evaluation sample is available.

## Operational limits

SQLite and demo-role headers are suitable for local demonstration, not production deployment. Resetting data is destructive. There is no production-system integration, production authentication, external-mail ingestion, or formal compliance/security certification.

## Added in the extension of the PoC

- Live AI is still untested: it needs an approved, EU-hosted OpenAI-compatible endpoint and key. Run `python scripts/live_ai_check.py` with `AI_PROVIDER` set to the live provider once available; the mock keyword classifier is not evidence of real accuracy.
- The taxonomy (8 categories, 11 causes), defaults, response targets and the category-level repeat match are drafts that need Renewi confirmation.
- The seeded history (45 complaints, about 36% `Other`) is synthetic and only demonstrates the dashboard; it is not evidence of the 10% `Other` target.
- Browser tests need Google Chrome installed and free ports 8010 and 5183.
