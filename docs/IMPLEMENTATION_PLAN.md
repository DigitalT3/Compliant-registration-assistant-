# Complaint Registration Assistant PoC: Implementation Plan

Source: PRD v0.2 (28 Oct 2026). Plan version: 1.0 (29 Oct 2026). Status: approved.

> **Update (29 Oct 2026):** the repo already contains a working PoC (PR #1). The build now **extends that code** instead of starting from scratch (decision D9 is superseded). See `docs/GAP_ANALYSIS.md` for what exists and the ordered fix plan. Sections 5-7 of this plan remain the target content (taxonomy, defaults, scenarios, data); apply them to the existing `config.json` and seed rather than adding parallel files.

Source tags follow the PRD: **[PRD]** is stated in the PRD, **[Plan]** is a decision or assumption made in this plan, **TO CONFIRM** needs an owner to verify. Every value that the PRD leaves open is a draft kept in a config file, never hard-coded.

---

## 1. Objective and principles

**Objective.** In one 24-hour build, deliver a desktop browser assistant on synthetic data that lets an employee start from whatever they have, confirm prefilled context, describe the complaint in their own words (Dutch or English), confirm an AI-suggested type and root cause, see repeat complaints under one configurable rule, and save to a PoC-only store, while logging everything needed to measure time, "Other" share, acceptance and prefill. [PRD §1, §4]

**Principles.**
1. Every Must requirement (FR-01, 03, 04, 05, 07, 08, 09, 10, 12, 14, 15, 16, 17) is built and demonstrable by hour 24; Should/Could items are built only after that. [PRD §11.1]
2. Scope is frozen at hour 0; new ideas go to the "after" list.
3. Synthetic data only; no personal data, no secrets in source, no write path to any live system.
4. The repeat rule is deterministic code, never an LLM decision.
5. The user always makes the final choice; every suggestion shows its reason; the AI never blocks manual registration.
6. What must carry over to production: flow, field mapping, repeat rule, root-cause list. All four live in config/docs, not buried in code. [PRD §11.2]
7. The app is labelled a demonstrator; a mock AI is always labelled as mock.

## 2. Decisions and assumptions

| # | Decision | Reason |
|---|---|---|
| D1 | Backend: Python 3.11+, FastAPI, SQLite, pydantic | Fast to build, one file DB, easy to delete after the readout [PRD §11.2] |
| D2 | Frontend: React + TypeScript (Vite), ECharts for charts | Lightweight desktop browser app [PRD §11.2] |
| D3 | AI behind a provider interface: `mock` (default offline), `openai_compatible` (any EU-hosted endpoint, incl. Azure OpenAI EU) | PRD: any EU-hosted model on synthetic data; keys come from env, never source |
| D4 | One AI call, `analyze`, returns suggested type + top-3 causes + summary (using the predicted type's template); a second, cheaper `summarise` call runs only if the user changes the type | Meets suggestions ≤ 3 s (NFR) and keeps steps 3 and 4 fast |
| D5 | In-app dashboard; Power BI only if Renewi asks for the readout [PRD FR-17] | Smaller scope |
| D6 | Named demo users picked from a list (no passwords) with a role and group; the backend enforces roles | PRD: named PoC users only; this is not production auth |
| D7 | Plain-form mode (no AI, still prefill and defaults) doubles as the AI-unavailable fallback and as a like-for-like timing comparison | PRD §7.1; §13 timing |
| D8 | All data is synthetic, but generated from a documented field list so real data can be swapped in later | PRD §10 |
| D9 | Repo is greenfield in this folder. If code from the other tool is brought over, it is reviewed against section 9 before reuse | The earlier plan's code is not in this repo |

**Draft inputs the PRD says are needed before the build, and the plan's placeholder for each** (all TO CONFIRM; replaced by Renewi's versions when they arrive, no code change needed):

| Input | Owner | Placeholder used |
|---|---|---|
| Registration field list and mandatory rules | Complaint system owner | Section 5.1 |
| Current/draft short root-cause list | Kwafie, Naomi, Maikel | Section 5.2 |
| Repeat definition | Juul | Section 5.4 (60 days, customer + site, level-1 cause, open + closed) |
| 10 typical complaints | Process owners | Section 6 (invented, NL/EN) |
| Defaults and templates per type | Process owners | Sections 5.3, 5.5 |

## 3. Architecture

```
React UI (nl/en) ──► FastAPI routers ──► Services ──► SQLite (PoC DB)
                          │                 ├─ lookup / prefill / defaults
                          │                 ├─ repeat rule (pure function)
                          │                 ├─ session + event logging
                          │                 └─ metrics
                          └──► AI service ──► mock | EU-hosted LLM ──► schema validation
Config (JSON, versioned): taxonomy, types, defaults, templates, repeat rule, roles, AI settings
```

**Repo layout.**
```
backend/    app.py, settings.py, db.py, seed.py, auth.py,
            services/ (lookup, prefill, repeat, complaints, sessions, metrics, ai/)
            routers/
config/     taxonomy.json, types.json, defaults.json, templates.json, repeat_rule.json,
            field_mapping.json, users.json
seed_data/  scenarios.json (10 scripted cases), generators
frontend/   src/ (features/register, history, dashboard, reference, test-session, config), i18n/
tests/      unit/, integration/, acceptance/, e2e/
docs/       IMPLEMENTATION_PLAN.md, TRACEABILITY.md, DEMO_SCRIPT.md, KNOWN_ISSUES.md, FIELD_MAPPING.md
```

**Read-only guard (FR-16).** No HTTP client or credential for any Renewi system exists in the code. An automated test scans the code and `.env.example` for outbound write clients and fails the build if any appear.

## 4. Data model (SQLite)

| Table | Purpose | Key columns |
|---|---|---|
| customers | Master | id, customer_no, name, active |
| sites | Master | id, customer_id, name, address, postcode |
| contracts | Master | id, customer_id, site_id, contract_no, service, start, end, active |
| orders | Last 90 days | id, customer_id, site_id, contract_id, order_no, container_no, service_date, status |
| complaints | Saved records, in the target-field structure (FR-14) | id (`POC-0001`), customer_id, site_id, contract_id, order_id, container_no, channel, complaint_date, registered_by, type, root_cause_l1, root_cause_l2, other_reason, description_original, language, summary_json, priority, status, owner_team, repeat_flag, repeat_count, linked_ids, taxonomy_version, rule_version, session_id, is_synthetic |
| root_causes / complaint_types | Loaded from config at seed time | id, level, parent, name_nl, name_en, definition, examples |
| repeat_checks | Evidence per registration | complaint draft key, matches JSON, rule_version, checked_at |
| repeat_disputes | FR-13 | complaint_id, linked_id, decision, reason, user, created_at, reviewed |
| sessions | One per registration attempt | id, user, group, mode (`assistant`/`plain`), participant_id, scenario_id, started, completed, saved, abandoned |
| step_events | Time per step | session_id, step, entered_at, left_at (server timestamps) |
| field_events | Provenance | session_id, field, source (`prefilled`/`default`/`typed`/`edited`/`blank`), value_changed |
| ai_events | Suggestions | session_id, op, provider, is_mock, latency_ms, status, suggestions JSON, chosen cause, outcome (`accepted_top1`/`accepted_top3`/`changed`/`other`/`manual`) |
| audit | Who did what | actor, action, entity, at |
| baseline | Timings of today's form (from stopwatch sessions) | group, scenario, seconds |
| exit_interviews | Would use daily? | participant_id, would_use_daily, comment |
| labels | Expert blind labels and summary ratings | complaint_id, rater, cause_label, summary_rating |

**Time is measured on the server** from step events; the client cannot submit totals.

## 5. Config content (drafts, all TO CONFIRM)

### 5.1 Field list (the PoC "target form")
Used for FR-14 mapping and the prefill-rate denominator.

| Field | Mandatory | Filled by |
|---|---|---|
| customer, site, contract, order, container no. | customer, site | Lookup |
| channel, complaint date, registering user | all | Default / session |
| type | yes | AI suggestion, user confirms |
| root cause (l1, l2), other reason | cause yes; reason if Other | AI suggestion, user confirms |
| priority, status, owner team | yes | Default per type |
| description (original text), summary | description yes | Typed; AI summary |
| repeat flag, count, links | auto | Repeat rule |

**Prefill rate = fields prefilled or defaulted ÷ total fields at save.** Of 16 fields, 12 are system-filled (customer, site, contract, order, container, channel, date, user, status, priority, owner team, repeat flag), which gives **75%** against the ≥ 70% target. [PRD §4.3]

### 5.2 Draft root-cause list (version `draft-0.1`, 7 categories + Other, with sub-causes)

| L1 category | L2 sub-causes |
|---|---|
| Missed or late collection | Route not completed · Vehicle breakdown · Access blocked · Wrong schedule · Container not presented |
| Container and equipment | Damaged · Missing · Wrong size or type · Not delivered · Overfilled by customer |
| Spillage and property damage | Spillage after emptying · Damage to property · Damage by vehicle |
| Invoicing and contract | Wrong invoice · Billed for no service · Rate dispute · Contract administration |
| Driver and crew conduct | Behaviour · Safety · Noise or timing |
| Communication and planning | No notification · Wrong information · Slow response |
| Weighing and waste acceptance | Weighing dispute · Rejected load · Wrong waste code |
| **Other** | Free reason required |

Each entry carries a Dutch and English name, a one-line definition and 2 examples (used by the mock AI and the live AI prompt).

### 5.3 Complaint types and defaults (FR-05)

| Type | Typical causes | Channel | Priority | Status | Owner team | Response target |
|---|---|---|---|---|---|---|
| Service failure | Missed/late, Communication | Phone | Normal | Open | Operations | 2 working days |
| Damage or incident | Spillage, Container, Damage | Phone | High | Open | Operations | 1 working day |
| Invoice or contract | Invoicing | Email | Normal | Open | Customer service | 5 working days |
| Conduct or communication | Driver conduct, Communication | Phone | Normal | Open | Customer service | 3 working days |

Defaults apply on type selection, never overwrite a field the user typed, and are documented in `config/defaults.json`.

### 5.4 Repeat rule (version `draft-juul-v1`, configurable)

| Parameter | Draft value |
|---|---|
| Match keys | Same customer and same site |
| Cause match | `level1` (switchable to `level2`) |
| Window | 60 days, inclusive of day 60, counted back from the new complaint's date |
| Earlier status | Open and closed |
| Missing site or cause | No flag; shows "cannot check: missing site/cause" |
| Output | Flag, count in window, linked complaint IDs with date, status and cause |

### 5.5 Summary templates (FR-08)
Every type's template has **What / Where / When / Impact**. Extras: Service failure adds *Expected vs. actual service date*; Damage adds *Container no. and extent*; Invoice adds *Invoice no. and amount disputed*; Conduct adds *Who/vehicle if known*. Missing information is shown as "not stated", never invented.

## 6. Synthetic data specification

**Generated by a seeded script, so every reset gives identical data** (`python -m backend.seed --reset`). Dates are relative to a fixed anchor date in config.

| Entity | Quantity and shape |
|---|---|
| Customers | ≥ 25 invented Dutch/Belgian company names; two share a prefix (e.g. "Van Dijk Recycling" / "Van Dijk Logistiek") to test ambiguity; one name has no match in orders |
| Sites | 1–4 per customer; 3 customers with ≥ 3 sites |
| Contracts | 1–2 active per site, one expired |
| Orders | ≥ 6 per site in the last 90 days, unique container numbers |
| Complaint history | ≥ 40 past complaints, over the last 6 months, mixed types, ~35% "Other" in history to mimic the 40% baseline |
| Users | 8 demo users across groups: Customer service ×2, Sales, Site operations ×2, Team lead, Process owner, Admin |

**The 10 scripted cases (T01–T10), the "10 of 10 at hour 24" test** [PRD §4.3, §13]

| ID | Scenario | Starts from | Expected result |
|---|---|---|---|
| T01 | Simple missed collection, single site | Customer no. | Match, prefill, cause *Missed or late*, no repeat |
| T02 | Dutch description, damaged container | Container no. | Dutch text accepted and summarised, cause *Container: Damaged* |
| T03 | Multi-site customer | Name | Pick list, most recent order first; site chosen |
| T04 | Seeded repeat | Order no. | Flags repeat, count 1, links earlier ID |
| T05 | Same customer, **different site** | Customer no. | No repeat flag |
| T06 | Same site and cause, **61 days earlier** | Customer no. | No repeat flag (boundary); a variant at day 60 does flag |
| T07 | Complaint that fits no category | Name | "Other" chosen, reason required, closest category shown |
| T08 | Pasted email (Should: FR-02) | Email text | Customer, order and text extracted |
| T09 | Vague, low-confidence text | Customer no. | Top 3 shown, nothing preselected |
| T10 | No match, then manual search | Typo'd name | No-match flow; continue with blank flagged customer fields |

Extra failure injections (not counted in the 10): AI timeout, AI invalid JSON, AI disabled (fallback to plain form), duplicate submit, "Other" without reason, same cause different category (no flag).

## 7. API outline

| Area | Endpoints |
|---|---|
| Health/config | `GET /health`, `GET /api/config` (taxonomy, types, defaults, rule, user list), `PUT /api/config/repeat-rule` and `/defaults` (Admin/Process owner; versioned and audited) |
| Lookup | `GET /api/customers/search?q=` (returns `match_type`, `candidates[]`), `GET /api/customers/{id}/context` (sites, active contracts, last 10 orders) |
| Prefill | `POST /api/prefill` (context + user → fields with provenance), `POST /api/defaults/apply` (type → default fields) |
| AI | `POST /api/ai/analyze`, `POST /api/ai/summarise`, `POST /api/ai/extract-email` (Should) |
| Repeat | `POST /api/repeat/check`, `POST /api/repeat/disputes` (Could), `GET /api/repeat/disputes` |
| Complaints | `POST /api/complaints` (one transaction), `GET /api/complaints`, `GET /api/complaints/{id}` |
| Sessions | `POST /api/sessions`, `POST /api/sessions/{id}/events`, `POST /api/sessions/{id}/complete` |
| Analytics | `GET /api/analytics/summary`, `GET /api/analytics/sessions`, `GET /api/export/sessions.csv`, `GET /api/export/labels-sample.csv` |
| Test support | `POST /api/baseline`, `POST /api/exit-interview`, `POST /api/labels` |

Errors use one envelope `{error:{code,message,request_id}}`; no stack traces; request-size limit.

## 8. Build plan

### Phase 0: Before the build (by Tue 3 Nov) [PRD §14]

- [ ] Confirm the build window (Wed 4 to Thu 5 Nov) and who the 1–2 builders are.
- [ ] Ask Glenn/Richard for the real field list, root-cause list, repeat definition and 10 typical complaints; if late, build on section 5 and 6 drafts.
- [ ] Check with Richard and the Salesforce PO for a planned form change (open question 7).
- [ ] Get an EU-hosted LLM key into `.env` (or confirm mock mode for the demo); confirm EU region.
- [ ] Usability walk-through of today's form (clicks, fields, system switches) to feed the baseline.
- [ ] Book 6–8 users and the on-site BA for the timed sessions.
- [ ] Confirm Python, Node and package install work on the build machine.
- [ ] Hour-0 scope freeze: Must list agreed, Should/Could list parked.

### Phase 1: The 24-hour build

| Hours | Block | Deliverables | Requirements | Exit check |
|---|---|---|---|---|
| 0–2 | Setup, data model, synthetic data | Repo scaffold, schema and migrations, config files, seed script, 10 scenarios, demo users, `.env.example`, read-only guard test | FR-14 (model), FR-16 | `seed --reset` twice gives identical row counts |
| 2–8 | Start, lookup, prefill, defaults | Search endpoint (4 input types, ambiguity, no match), context endpoint, prefill with provenance, defaults per type, step 1 and 2 UI, stepper shell, nl/en switch, demo-user picker, session and step-event logging started | FR-01, 03, 04, 05, (06 provenance data) | T01, T03, T10 pass; lookup ≤ 2 s |
| 8–14 | Describe and classify | AI provider interface, mock provider, live provider, JSON schemas, `analyze`/`summarise`, fallback to plain form, top-3 with reasons, low-confidence no-preselect, "Other" reason and closest-category re-show, step 3 and 4 UI | FR-07, 08, 09, 10 | T02, T07, T09 pass; suggestion ≤ 3 s; AI-down fallback works |
| 14–18 | Repeat, save, logging, guard | Repeat rule service and endpoint with evidence panel, atomic save with `POC-` ID, field and AI events, audit, review-and-save UI, history page | FR-12, 14, 15, 16 | T04, T05, T06 pass; no live write path test passes |
| 18–21 | Dashboard | Metrics: time per registration (and per step), "Other" share, suggestion acceptance (top-1/top-3/changed), prefill rate, repeat rate, by user group; sample sizes and empty states; baseline comparison; CSV export | FR-17 | Numbers match a hand count from the log on 10 registrations |
| 21–24 | Test, fix, demo | Run T01–T10 end to end in the browser, fix, record results, demo script, README | All Musts | **10 of 10 scripted cases pass; Must checklist (section 12) all ticked** |

**Cut-lines.** If a block overruns by more than 1 hour, drop in this order: Could (FR-11, FR-13), then Should (FR-06 visual markers, FR-02 email extraction). Never drop a Must. FR-06's provenance data is still logged (it feeds FR-15) even if the visual marker is dropped.

**After the Musts (only if time remains), in order:** FR-06 markers, FR-02 email extraction, FR-13 disputes, FR-11 two-level storage/UI, summary-rating and expert-label pages.

### Phase 2: After the build (by Fri 13 Nov) [PRD §13, §14]

- [ ] Timed sessions: 2–3 employees per group × 3 groups × 5 complaints, on today's form and on the PoC, with the same scenarios; record baseline via `/api/baseline`.
- [ ] Capture exit interviews (target: 5 of 6–8 would use daily).
- [ ] Process owners rate 10 summaries (target ≥ 8 usable) and blind-label a sample for cause accuracy (target ≥ 85%).
- [ ] Reset targets from the real baseline; report time, "Other" share, acceptance, prefill, repeat results.
- [ ] Once the DPA allows real data: FR-18 clustering, FR-19 shorter list v1, FR-20 re-label 200 records (see section 14).
- [ ] Readout with Glenn: go / adjust / stop. Delete the PoC DB afterwards unless Renewi asks otherwise.

## 9. Requirement traceability (all 20 FRs)

| FR | Priority | Where built | Acceptance check |
|---|---|---|---|
| FR-01 | Must | `lookup` service, search endpoint, step 1 | T01, T02, T03: customer no., order, container, name each match in ≤ 2 s (timed test) |
| FR-02 | Should | `ai/extract` | T08; ≥ 8 of 10 typical complaints find the right customer |
| FR-03 | Must | Context endpoint, step 1 panel | Sites, active contracts, last 10 orders equal seed for 20 customers (automated) |
| FR-04 | Must | `prefill` service | All 7 prefill fields filled when matched; each editable |
| FR-05 | Must | `defaults.json`, `defaults/apply` | Documented per type; applied on type selection; never overwrites typed values |
| FR-06 | Should | `field_events`, UI badges | Marker per field; present in the log |
| FR-07 | Must | Step 3 textarea | NL and EN stored exactly as typed (T02) |
| FR-08 | Must | `ai/summary`, templates | Editable summary; ≥ 8 of 10 rated usable (Phase 2) |
| FR-09 | Must | `ai/classify` | Top 3 with one-line reasons in ≤ 3 s; acceptance logged |
| FR-10 | Must | Save validation (UI and API) | API rejects "Other" with no reason (test) |
| FR-11 | Could | `level2` in taxonomy; both levels stored | Both stored |
| FR-12 | Must | `repeat` service | 100% seeded repeats flagged; 0 false flags (T04, T05, T06 and variants) |
| FR-13 | Could | `repeat_disputes` | Dispute with reason logged for Juul's review |
| FR-14 | Must | `complaints` table, `field_mapping.json` | Saved record maps one-to-one to the field list (mapping test) |
| FR-15 | Must | `sessions`, `step_events`, `field_events`, `ai_events` | Log complete for every test registration (test asserts non-empty rows for every step) |
| FR-16 | Must | Code and config | No write credentials or clients exist (static test) |
| FR-17 | Must | Analytics and dashboard | Five metrics shown by group; numbers verified against the log |
| FR-18 | Must (after) | Later phase, section 14 | Themes cover ≥ 90% of "Other" |
| FR-19 | Must (after) | Later phase | List v1 agreed by Kwafie, Naomi and Maikel |
| FR-20 | Should (after) | Later phase | ≥ 85% on 200 records |

## 10. Alternative flows checklist [PRD §7.1]

| Situation | Behaviour to implement | Covered by |
|---|---|---|
| No match | Search by name/postcode offered; continue with blank, flagged customer fields | T10 |
| Several matches | Short pick list, most recent order first | T03 |
| Low confidence (< threshold, draft 0.5) | Top 3, no preselection, user must choose | T09 |
| "Other" | One-line reason required, closest category shown again, reason stored for the taxonomy review | T07 |
| Repeat detected | Earlier complaints with date, status, cause; confirm or dispute with reason (Could) | T04 |
| AI unavailable | Plain form with prefill and defaults, session marked `mode=plain` and AI failure logged | Failure injection |

## 11. Non-functional requirements [PRD §12]

| Area | How it is met and checked |
|---|---|
| Data protection | Synthetic data only; `is_synthetic` flag; no real data in repo |
| Security | Demo users with server-checked roles; audit log; no write path to live systems; secrets only in `.env` |
| Performance | Lookup ≤ 2 s and AI suggestions ≤ 3 s asserted in tests; AI timeout set just above 3 s, then fallback |
| Language | Interface strings in `nl.ts` and `en.ts`; Dutch and English free text accepted and summarised in the input language |
| Availability | Fallback to plain form if the model is down |
| Code quality | Readable, typed, README, kept in the DT3 repo; not hardened |
| Transparency | Each suggestion shows its reason; mock AI labelled in banner and API; the user always makes the final choice |
| Not covered by design | Mobile; production hosting; hardening |

## 12. Definition of done (Must checklist at hour 24)

- [ ] `seed --reset` reproducible; app starts from the README in one go
- [ ] FR-01 one search box, four input types, ≤ 2 s
- [ ] FR-03 sites, contracts and last 10 orders
- [ ] FR-04 prefill with every field editable
- [ ] FR-05 defaults per type documented and applied
- [ ] FR-07 NL and EN accepted
- [ ] FR-08 editable structured summary from the type template
- [ ] FR-09 top 3 causes with reasons ≤ 3 s; low confidence handled
- [ ] FR-10 "Other" needs a reason (UI and API)
- [ ] FR-12 repeat rule, evidence shown, seeded cases correct
- [ ] FR-14 record saved in target structure; retrievable
- [ ] FR-15 complete log per registration
- [ ] FR-16 read-only guard test passes
- [ ] FR-17 dashboard with five metrics by group
- [ ] T01–T10 pass in the browser (10 of 10); results recorded honestly
- [ ] Dutch/English interface switch works
- [ ] AI-down fallback demonstrated
- [ ] Demo script and README written; known issues listed

## 13. Measurement support [PRD §4.3, §13]

| Success criterion | How the PoC supports measuring it |
|---|---|
| Built in 24 hours, 10/10 cases | Section 12 checklist and the recorded T01–T10 run |
| Time per registration, ≥ 50% faster, aim < 90 s | Server-timed step events; session has `mode` (`assistant` vs `plain`), participant and scenario; baseline table holds today's-form stopwatch times; dashboard compares |
| "Other" < 10% | Dashboard share from saved test registrations |
| Top-3 acceptance ≥ 70% | `ai_events.outcome` |
| Cause accuracy ≥ 85% | Blind-label CSV export and label entry; agreement computed |
| Prefill ≥ 70% | Prefill rate formula in 5.1 (75% expected) |
| Repeats 100% flagged | Seeded cases in the automated acceptance tests |
| Would use daily ≥ 5 of 6–8 | Exit-interview capture |
| Summary usable ≥ 8 of 10 | Summary rating capture |

**Test-session mode:** the registration page has an optional "test session" panel (participant ID, group, scenario) so the BA can start, time and tag sessions without developer help.

## 14. Later phase on real data (not part of the 24 hours)

Blocked until the DPA allows real data. Plan only; no build now.
- FR-18: extract 12 months of cases (type, cause, free text, timestamps, creator role, status), cluster "Other" text into themes with an LLM in Renewi's EU Azure tenant, map themes to categories; target ≥ 90% coverage.
- FR-19: propose the shorter list with definition and examples; review with Kwafie, Naomi and Maikel.
- FR-20: re-label 200 historic complaints with the new list; target ≥ 85% agreement.
- The same fields in section 5.1 and the config files mean the real export loads without changing the app.

## 15. Testing strategy

| Level | Content |
|---|---|
| Unit | Seed reproducibility; lookup classifier (customer no./order/container/name); prefill provenance; defaults never overwrite typed; repeat rule (window boundary day 60 vs 61, other site, other customer, other cause, status filter, missing keys, multiple matches); AI schema validation; metrics math |
| Integration | API flow end to end; atomic save with forced-failure rollback; AI fallback (timeout, invalid JSON, provider off); role checks (403); "Other" without reason rejected; read-only guard; performance asserts |
| Acceptance | T01–T10 at API level, each tagged with its FR IDs |
| E2E (browser) | All 10 scripted cases through the UI, plus language switch |
| Manual | Demo run-through; check the dashboard against a hand count |

Rule: nothing is recorded as passed unless it was run; raw output goes in `docs/TEST_RESULTS.md`.

## 16. Risks and mitigations [PRD §16, plus build-level]

| Risk | Mitigation |
|---|---|
| Inputs late | Section 5 drafts, all in config; correct them in the user test |
| 24 hours not enough | Hour plan, cut-lines in section 8, Musts first, scope frozen at hour 0 |
| Mock AI mistaken for the real model | Banner and API label; accuracy only ever reported on the live provider or expert labels |
| LLM slow or wrong | 3 s timeout then fallback; top 3, no auto-select at low confidence; accuracy measured |
| No LLM key at build time | Mock provider is complete enough to demo; live mode is one env change |
| Demonstrator mistaken for a product | Banner, README, docs say so |
| Users not released | Book them in Phase 0 |
| Time saved is in steps the PoC does not touch | Step-level timing shows where time goes; the build is cheap to redo |
| Repeat rule changes | Values live in `repeat_rule.json` with a version stamped on each record |

## 17. Open questions to resolve (from PRD §17 and this plan)

1. Which system holds complaints (assumed Salesforce cases)? Owner: Glenn / Renewi IT.
2. Which user groups register complaints, and how many a month? Owner: Glenn / Anniek.
3. Does 3–10 minutes cover registration only? Owner: Glenn.
4. Period and scope of the 40% "Other"? Owner: Kwafie / Naomi / Maikel.
5. Who owns the root-cause list and can approve a shorter one? Owner: Glenn.
6. Repeat definition and parameters? Owner: Juul.
7. A form change already planned? Owner: Richard / Salesforce PO.
8. Synthetic data fine for the build; when can real data be used? Owner: Richard / DPO.
9. **Build-team decisions:** LLM provider and key for the demo; who the 1–2 builders are; whether to bring over the other tool's code (D9).
