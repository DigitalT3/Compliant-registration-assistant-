# Scope of the PoC (PRD section 6)

This page maps every scope line to what the project does and the rule to keep. `tests/unit/test_scope_guard.py` checks the rules that can be checked automatically.

## In scope

| Scope line | How the project covers it |
|---|---|
| Working assistant built in 24 hours with AI-assisted coding | The registration flow with the assistant (steps 1 to 6). |
| Synthetic data shaped like the real complaint fields | `backend/seed_data`, `backend/field_mapping.json`. The banner says "synthetic data only"; `synthetic_only` is set in the API. |
| Draft shorter root-cause list and the repeat rule as build inputs | In `config.json`, both marked provisional until the process owners agree the list and Juul signs off the rule (Root causes and Configuration pages). |
| Timed test with 6 to 8 users: today's form against the PoC | Session timing, baseline entry, plain mode, `scripts/run_usertest.sh` (clean data). |
| Simple dashboard of the test results | Dashboard, per-employee table, Readout page, CSV exports. |
| After the build: 12-month analysis and root-cause list v1, once real data may be used | `scripts/field_profile.py` runs outside the app on an export; the cause-list agreement ("agree v1") is in the app. |

## Out of scope: rules to keep

| Out of scope | Rule |
|---|---|
| Any change to the live complaint system; live integration or write-back | The app has no connection to Renewi systems. Its only outbound call is to the language model (`backend/services/ai.py`). Do not add others. |
| Production-grade code, hosting or support | The PoC runs on a laptop or one small test host. `Dockerfile`, `fly.toml` and `docs/DEPLOY.md` are a convenience for the test, not a production set-up; there is no support or monitoring. |
| Real complaint data in the build | No real data in the repository, the database or the seed. Testers use made-up scenarios only (the banner says so), because typed text goes to the language model. A real export may be profiled with `scripts/field_profile.py`, but keep the file outside the repository. The report prints no values. |
| Handling after registration; roll-out and training | No complaint handling, assignment, status workflow or training material. |
| Mobile app | A browser app for a desktop. The layout adapts to narrow screens but is not designed or tested for phones. |

## Automatic checks
- No CSV, spreadsheet or database file is tracked by git.
- Only `backend/services/ai.py` makes outbound network calls.
- The API reports `synthetic_only` and the banner text keeps saying synthetic data only.
