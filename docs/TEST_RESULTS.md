# Test Results

## Executed evidence

| Command or activity | Observed result |
| --- | --- |
| `python -m pytest -q` | 24 passed in 15.17 seconds. |
| Frontend Chromium Playwright journey | 1 passed in 5.1 seconds. |
| `npm run build` | Passed in 1.26 seconds. |
| Isolated synthetic lookup measurement | 10.46 ms. |
| Isolated synthetic mock-classification measurement | 10.97 ms. |

The Python suite, browser journey, build, and performance checks were separate executions. They must not be represented as one fresh combined run.

## Coverage represented by the browser journey

`frontend/e2e/test_registration_journey.spec.ts` verifies customer lookup, explicit site selection, service-type phone default, mock summary and classification, seeded `POC-SEED-1` repeat evidence, review, and PoC-only save in Chromium.

## Qualifications

All executed tests use synthetic data and mock AI. Live AI was not tested because credentials were unavailable. No real-user evaluation, baseline time-saving comparison, expert agreement study, or production-system integration test has been performed. The runtime interactive browser-control tool was unavailable; the successful Playwright Chromium run is the browser interaction evidence.
