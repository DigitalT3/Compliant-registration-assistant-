# Known Issues and Handover Limitations

## Incomplete or unverified items

Live AI mode requires approved credentials and has not been tested. The deterministic mock provider demonstrates integration and fallback behaviour only; it is not evidence of summary quality, classification accuracy, calibrated confidence, or real-world performance.

The PoC uses a provisional taxonomy, field mapping, required-field set, defaults, and repeat rule. The dashboard calculates from recorded PoC events, but no real-user sessions, current-process baseline, or validated time-saving result exists. FR-18 through FR-20 have working tooling (screen Root-cause analysis, `/api/rca`, `scripts/rca.py`) proven only on synthetic data; their acceptance checks still need approved real "Other" text, the three process owners' agreement and 200 expert-labelled complaints.

## Operational limits

SQLite and demo-role headers are suitable for local demonstration, not production deployment. Resetting data is destructive. There is no production-system integration, production authentication, external-mail ingestion, or formal compliance/security certification.

## Added in the extension of the PoC

- Live AI (Bedrock) ran once in `us-east-2` with a `global.` inference profile, which is NOT EU-only; switch to an EU region and `eu.` profile before any real data. Only the OpenAI-compatible provider remains untested. Original note: it needs an approved, EU-hosted OpenAI-compatible endpoint and key. Run `python scripts/live_ai_check.py` with `AI_PROVIDER` set to the live provider once available; the mock keyword classifier is not evidence of real accuracy.
- The taxonomy (8 categories, 11 causes), defaults, response targets and the category-level repeat match are drafts that need Renewi confirmation.
- The seeded history (45 complaints, about 36% `Other`) is synthetic and only demonstrates the dashboard; it is not evidence of the 10% `Other` target.
- Browser tests need Google Chrome installed and free ports 8010 and 5183.
- Timing before 2026-10-29 starts at the customer choice, not when the form opened, so earlier sessions under-count the time spent finding the customer. Sessions recorded after the change include it (up to the 10-minute idle cap).
- A registration left idle for more than 30 minutes (`ABANDON_AFTER_MINUTES`, default 30) is marked abandoned by the next dashboard view, but its owner can still carry on and save: the session is resumed (audit entry `session_resumed`). Its step time counts the pause at most once at the 10-minute cap, but its total registration time includes the whole pause, so exclude sessions with a `session_resumed` entry from timing results.
- The per-employee view reports on named people. Agree with Renewi (and, in the Netherlands, check whether the works council or privacy officer must approve) before using it with real staff; `report.show_employee_names` in `config.json` can be set to false so that people appear as "Employee 1, 2, ...". Registrations resumed after a long pause (audit `session_resumed`) include the pause in their total time.
- An agreed proposed list can be made the live cause list from the Root-cause analysis screen (admin or a process owner), and the previous list restored; an administrator or business owner can freeze the list. The old causes stay on file as "retired" and count under the category that replaced them, so saved registrations and the repeat check keep working. Limits: the mapping follows the proposal's own grouping (the model's), the dashboard still lists a retired cause under its old name, and a change is blocked while someone is mid-registration. Not tried on real data.
