# Gap Analysis: Existing PoC vs PRD v0.2

Reviewed 29 Oct 2026 against PRD v0.2 and `docs/IMPLEMENTATION_PLAN.md`. Scope of the review: the code merged in PR #1 (`backend/`, `frontend/`, `tests/`, `config.json`, `docs/`).

## 1. What was actually run

| Check | Result |
|---|---|
| `pytest` (backend: unit, integration, acceptance) | 24 passed in 2.1 s |
| Frontend `tsc --noEmit` and `vite build` | Both pass |
| Browser E2E (Playwright), live app smoke, live AI | **Not run in this review** |

Everything below comes from reading the code, config and docs plus the two runs above.

## 2. What already meets the PRD

| Area | Evidence |
|---|---|
| FR-01, FR-03 lookup by customer no., order, container, name; ambiguity and no-match handled; context shows sites, contracts, last 10 orders | `services/lookup.py`, `routers/customers.py` |
| FR-04 prefill with per-field provenance (prefilled / default / manual / edited / blank) | `services/prefill.py` |
| FR-07 Dutch and English | UI i18n, language detect, tests |
| FR-09, FR-10 top-3 causes with reasons, low confidence preselects nothing, "Other" needs a reason (UI and API) | `services/ai.py`, `Register.tsx`, acceptance tests |
| FR-12 repeat rule: pure function, configurable, inclusive boundary, status filter, missing keys | `services/repeat.py`, 11 boundary scenarios (T10–T20) |
| FR-14, FR-16 PoC-only atomic save; no live write path | `services/complaints.py`, tests |
| FR-15 sessions, step events, field events, AI events | migrations, `services/sessions.py` |
| FR-17 dashboard backend: duration, step times, top-3 rate, Other share, repeat rate, AI success | `services/metrics.py` |
| Fallback when AI fails; AI output schema-validated; mock labelled MOCK | `services/ai.py` |
| Role checks, demo users, error envelope, 6-step stepper, nl/en | `auth.py`, `App.tsx` |

## 3. Gaps, ordered by risk to the PRD success criteria

### P1: puts a PRD target or Must requirement at risk

| # | Gap | Evidence | PRD impact | Fix |
|---|---|---|---|---|
| G1 | **Prefill-rate metric is wrong.** It counts only `prefilled` events in the numerator, not defaults, and the PRD target is "prefilled **or defaulted**" ≥ 70% | `metrics.py` line 90 | Target can read low even when met | Count prefilled + default |
| G2 | **Defaults are thin.** Only `channel` is defaulted, for 3 types. No priority, status, owner team or response target | `config.json` `defaults` | FR-05 "defaults per type" only weakly met; ≥ 70% prefill unlikely | Extend defaults per type; add fields to the model and field mapping |
| G3 | **Flow is slower than needed.** Describe needs a "Summarise" click, Classify needs a separate "Classify" click, then Next. Two AI calls, three clicks | `Register.tsx` steps 3–4 | Threatens the < 90 s target | One `analyze` call when leaving Describe; show summary and top 3 together; preselect top-1 only when confident |
| G4 | **One generic summary template**, not per type (what/where/when/impact only). Mock summary is just the first sentence | `config.json` `summary`, `ai.py` `_summarise` | FR-08 "from the template for the complaint type" | Per-type templates with extras; summary generated after type is known; re-summarise on type change |
| G5 | **AI timeout is 10 s with 1 retry**, so a bad call can take about 20 s | `config.json` `ai` | NFR suggestions ≤ 3 s | Timeout ~3.5 s, no retry on classify |
| G6 | **No way to run the timed test.** UI has no participant/group/scenario tagging, no assistant-vs-plain mode, no per-group baseline (single number only), no exit interview, no CSV export. Dashboard UI shows no by-group view even though the API supports `group_by` | Frontend grep: 0 hits for scenario, participant, group_by, csv | §13 measurement protocol; FR-17 "by user group"; "≥ 5 of 6–8 would use daily" | Test-session panel; `mode` on sessions; baseline table; exit-interview capture; dashboard group view and comparison; CSV export |
| G7 | **Browser coverage is one journey.** 20 scenarios are tested at API level; one Playwright spec exists | `frontend/e2e/` (1 file) | "10 of 10 scripted cases at hour 24" | Browser E2E for the 10 headline cases |

### P2: weakens the demo or a Should/Could item

| # | Gap | Evidence | Fix |
|---|---|---|---|
| G8 | **Seed is thin and generic.** 15 history complaints (plan: ≥ 40), 4 of 15 "Other" (27%, not ~40%), names like "Fictional Delta Works 01", every order at a site shares one container number | `backend/seed.py` | Richer history, realistic fictional names, unique containers |
| G9 | **No postcode search**, though PRD §7.1 offers "search by name or postcode" on no match | `services/lookup.py` | Add postcode fallback |
| G10 | **FR-02 email paste has no UI.** Endpoint exists, nothing calls it | Frontend grep: 0 hits for extract/paste | Paste box on step 1 |
| G11 | **FR-13 dispute has no button in the registration flow**, only a backend endpoint and a list on another page | `Register.tsx` step 5 | Confirm/dispute with reason on the repeat panel |
| G12 | **Taxonomy is flat**: level 1 equals the complaint type, so "level 2" repeat mode is just exact cause. Only 3 types, 8 causes (no spillage, weighing, etc.) | `config.json` `root_causes` | Two-level list (category → sub-cause) per the plan draft; `cause_mode` default `level1` per PRD §9 |
| G13 | **Blind labelling and summary rating**: an evaluation page exists, but no sample export and no hiding of the AI's cause from the rater | `routers/review.py`, `App.tsx` Evaluation | Labelling sample export; blind view |
| G14 | **Mock extraction and detection are fitted to the seed formats** (`100\d{3}`, `ORD-…`, `BOX-…`; small Dutch word list) | `ai.py` | Keep for mock; make patterns config-driven; real provider covers general text |

### P3: documentation and process

| # | Gap | Fix |
|---|---|---|
| G15 | `docs/TRACEABILITY.md` marks FR-02 and FR-13 "Tested", but neither is usable from the UI, so "Tested" overstates | Re-grade statuses after fixes |
| G16 | No single "run the app" command; frontend deps and Playwright browsers are manual | README quick-start, one run script |
| G17 | Live AI untested (no credentials); PRD acceptance (≥ 85% accuracy, ≥ 8 of 10 summaries usable) cannot be shown on the mock | Needs an EU-hosted model key; a smoke script to exercise it |
| G18 | Anchor date is fixed at 2026-10-28 and clock mode is `fixed` | Keep for repeatable demos; document; set the anchor near the demo date |

## 4. Fix plan (extend, not rebuild)

| Order | Work | Gaps | PRD block it supports |
|---|---|---|---|
| 1 | Defaults and fields, prefill-rate fix, richer seed, postcode search | G1, G2, G8, G9 | 0–8 h (prefill/defaults) |
| 2 | Single `analyze` call, per-type templates, AI timeout, auto-summary then classify in one step | G3, G4, G5 | 8–14 h (describe, classify) |
| 3 | Two-level taxonomy, dispute UI, email paste UI | G10, G11, G12 | 14–18 h |
| 4 | Test-session panel, plain mode, baseline, exit interview, dashboard by group, CSV | G6, G13 | 18–21 h (dashboard) |
| 5 | Browser E2E for 10 headline cases, run everything, re-grade traceability, README run script | G7, G15, G16 | 21–24 h |
| Needs you | EU-hosted LLM key and endpoint for live mode | G17 | Before the demo |

All existing tests must still pass after each step; each step adds tests for what it changes.
