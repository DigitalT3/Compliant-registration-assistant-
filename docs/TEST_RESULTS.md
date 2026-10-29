# Test Results

## Executed evidence

| Command or activity | Observed result |
| --- | --- |
| `python -m pytest -q` | 61 passed in about 7 seconds. |
| `npx playwright test` (system Chrome) | 14 passed in about 15 seconds. |
| `npx tsc --noEmit` and `npm run build` | Passed. |

These were separate executions on 2026-10-29, not one combined run.

## Browser scripted cases (`frontend/e2e/scripted_cases.spec.ts`)

T01 customer-number registration with the suggested cause confirmed and saved; T02 order number prefill; T03 container lookup; T04 ambiguous name (nothing auto-chosen); T05 no match then postcode; T06 Dutch complaint; T07 invoice type switch and defaults; T08 low confidence blocks save; T09 `Other` needs a reason; T10 seeded repeat with a recorded dispute; T21 pasted email; T22 plain-form mode (no AI); T23 dashboard with the plain/assistant split; T24 Dutch interface.

The first browser run found a real defect: the suggestion list and the all-causes list shared one radio group, so a suggested cause showed as unchecked. It was fixed (separate groups) and covered by T01, T06 and T10. The other first-run failures were wrong selectors in the tests.

## Qualifications

All executed tests use synthetic data and the labelled mock AI. Live AI was not tested because no endpoint or credentials were available (`scripts/live_ai_check.py` is ready for when they are). No real-user evaluation, baseline time-saving comparison, expert agreement study, or production-system integration test has been performed; the dashboard targets will show "no data" or "indicative" until test sessions are recorded.
