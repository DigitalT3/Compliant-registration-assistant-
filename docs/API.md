# API Reference

## Access and errors

The API is served by FastAPI. Generated OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`. Protected routes use the PoC-only `X-Demo-User` header. Errors use `{ "error": { "code", "message", "request_id" } }`.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | PoC, synthetic-data, clock, and AI-mode status. |
| `POST /api/config/root-causes/review` | `review_taxonomy` (the process owners, role evaluator) | `{decision: agree|changes, comment?}`; a request for changes needs a comment. Returns the status of the list. `GET /api/config/root-causes` includes `review`: `state` (`draft`, `changes_requested`, `agreed`), `agreed` of `required` (`taxonomy_review.required_agreements`, 3), each person's latest review, and the fingerprint of the list. A review counts only for the exact list it was given on: change the list and the agreement starts again. |
| `POST /api/config/repeat-rule/signoff` | `sign_off_rule` (the rule owner, role `rule_owner`) | `{decision: sign_off|changes, comment?}`. `GET /api/config/repeat-rule` includes `signoff` (`draft`, `changes_requested`, `signed_off`). A sign-off counts for the exact rule parameters; editing the rule (`PUT /api/config/repeat-rule`, now `edit_rule`: admin and rule owner) voids it. |
| `GET /api/readout`, `GET /api/export/readout.csv` | `readout` (business owner, evaluator, admin) | Targets with sample sizes, the baseline comparison, open conditions (cause list, rule sign-off, data volumes, baseline) and recorded decisions. No verdict is computed. |
| `POST /api/readout/decision` | `decide` (business owner only) | `{decision: go|conditional|no_go, comment}`; the comment is required. Stored with the targets and conditions it was based on. |
| `GET /api/config`, `/defaults`, `/root-causes`, `/repeat-rule` | Effective non-secret configuration and provisional metadata. |
| `PUT /api/config/repeat-rule`, `/defaults` | Update configuration; requires `configure`. |
| `GET /api/customers/search?q=` | Search by customer number, order, container, or name. |
| `GET /api/customers/{id}` and `/{id}/context` | Customer, site, contract, and order context. |
| `POST /api/prefill` | Editable prefill and provenance. `guess_site: true` (sent when a customer is chosen) fills the site from the customer's latest order when the search gave none, and with it the contract, order and container. The registration date is today's real date (Europe/Amsterdam), not the fixed demo clock. |
| `GET /api/users/colleagues` | `register` permission. Names only (`id`, `name`) of active accounts that can register complaints, so the registering user can be changed. |
| `POST /api/complaints/extract`, `/summarise`, `/classify`, `/check-repeat` | AI-assisted extraction, summary, classification, and deterministic repeat check. `extract` also returns `customer_query` and `matched_by`: a customer, order or container number that exists in the data, otherwise the company name or postcode found in the text (the screen searches with `customer_query`). `python -m scripts.email_eval` runs the ten typical e-mails of FR-02 (`tests/acceptance/email_cases.json`) against the configured model. |
| `POST /api/complaints`; `GET /api/complaints`; `GET /api/complaints/{id}` | PoC-only complaint persistence, history, and detail. Optional `registration_date` (YYYY-MM-DD, not in the future, at most a year back) and `registering_user` (a colleague's id); left out they are today and the signed-in user. Registering for a colleague is written to the audit log (`registered_for`). |
| `POST /api/sessions`, `/api/sessions/{id}/events`, `/complete` | Session and event recording. |
| `GET /api/analytics/summary`, `/sessions` | Recorded metrics and session records; requires `analytics`. A **team lead** only gets the team they lead (a `group` in the request is ignored; the summary carries `scope.team`); a lead without a team gets 403 `team_required`. Admins and evaluators get every team. Each step counts at most `metrics.step_idle_cap_seconds` (600) **per visit** (going back and forth adds the visits up); the summary's `step_seconds` gives mean, median and n per step, and steps recorded under the old names `check_repeats` / `review_save` count as `repeat_save`. |
| `POST /api/sessions` | Starts a session. `opened_seconds_ago` (optional) is how long the form had been open when the customer was chosen; the session starts that long before (at most `metrics.step_idle_cap_seconds`), so time spent finding the customer is part of the registration time. |
| `GET /api/analytics/employees` | How each employee registers: saved and started registrations, median time with min and max, how often the assistant's summary and cause were kept, top-3 share, "Other" share, prefill rate, repeat share and the repeat decisions, plus a `team` block to compare with. Requires `analytics`; a team lead only gets the people of the team they lead. Shares based on fewer than `report.per_employee_min_n` (3) registrations come back as `value: null`. With `report.show_employee_names` off people appear as "Employee 1, 2, ..." and no ids are returned. |
| `GET /api/export/employees.csv` | The same table as one row per employee (first row: the team), same limits, for Power BI. |
| `GET /api/export/sessions.csv`, `/suggestions.csv` | Per-session timings (with `first_field_s`, the seconds from opening the form to the first field filled, and `first_entry_s`, to the first field the employee entered or changed); and one row per tracked field of every saved complaint (`team`, `field`, `origin`, `outcome` = accepted / changed / typed / empty) for Power BI. Same team scoping as the dashboard. |
| `POST` and `GET /api/repeat-disputes`; `POST` and `GET /api/evaluations` | Repeat review and expert evaluation. |
| `GET /api/analysis/other-reasons` | Synthetic-only exact-text grouping for later-phase readiness. |

## Example

```bash
curl -H "X-Demo-User: demo.emp.a1" \
  "http://127.0.0.1:8000/api/customers/search?q=100001"
```

Complaint creation requires `customer_id`, `description`, `complaint_type`, `root_cause`, and `channel`. The root cause must exist in the active taxonomy, references must belong to the customer, and `other_reason` is required when `root_cause` is `other`.

## Accounts and users

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `GET /api/auth/options` | public | Function categories, password length, whether approval and demo mode are on |
| `POST /api/auth/register` | public | `{name, email, password, function}`; creates an employee account, `pending` when approval is required |
| `POST /api/auth/login` | public | `{email, password}` returns `{token, expires_in, user}`; generic error for wrong e-mail or password, 403 while pending or disabled, 429 when locked |
| `GET /api/auth/me` | signed in | Profile and permissions |
| `POST /api/auth/logout` | signed in | Recorded in the audit trail (the token simply expires) |
| `POST /api/auth/change-password` | signed in | `{current_password, new_password}`; ends all older sessions and returns a new token |
| `POST /api/users` | `users` (admin) | `{name, email, function?, role}` (`function` is required for a lead: the team they lead); creates an active account and returns a one-time `temporary_password` (must be changed at first sign-in) |
| `POST /api/users/{id}/reset-password` | `users` (admin) | New one-time temporary password; unlocks the account |
| `GET /api/users?status=` | `users` (admin) | List accounts, pending first |
| `PATCH /api/users/{id}` | `users` (admin) | `{status, role, user_group, function}`; a lead must have a team (`function`, 422 `team_required`); the last active admin cannot be disabled or demoted, and nobody can disable themselves |

Send `Authorization: Bearer <token>`. While a temporary password is in use, every endpoint except `/api/auth/me`, `/api/auth/change-password`, `/api/auth/logout` and `/api/auth/options` answers 403 `password_change_required`. The `X-Demo-User` header is accepted only while `POC_DEMO_MODE=1`.

## Customer data (permission `customer_data`: employee, admin)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/customers/{id}/context?all=true` | Sites, contracts, orders (up to 200 with `all`, otherwise 10) and containers |
| `GET /api/customers?q=&limit=&offset=` | All customers with counts of sites, contracts, orders and containers |
| `POST /api/customers` | `{name, postcode?, first_site?}`; next customer number (`100035`), id `C035`; an optional first site is created as `C035-S1` |
| `GET /api/customer-data/{sites|contracts|orders|containers}?customer_id=&q=&limit=&offset=` | Rows across all customers (or one), each with `customer_name` and `customer_number`; `{items, total, limit, offset}` |
| `POST /api/customers/{id}/sites` | `{name, postcode?}`; id `C009-S3`, reference `SITE-009-3` |
| `POST /api/customers/{id}/contracts` | `{site_id, valid_from?, valid_to?}`; defaults to today and one year; status active or expired |
| `POST /api/customers/{id}/containers` | `{site_id, number?}`; an empty number is generated (`BOX-009-3`); unique, case-insensitive |
| `POST /api/customers/{id}/orders` | `{site_id, container, contract_id?, date?}`; the container and contract must belong to the site; reference `ORD-009-P1` |

Added rows carry `source='poc_added'`, `created_by` and `created_at`, and an audit entry `customer_data_added`. A container added without an order can still be found by its number in the search.

## Summary rating (FR-08)
`GET /api/evaluations/sample` (evaluate permission): saved PoC complaints this rater has not rated yet, with the text, the summary (what, where, when, impact, `extras`) and no cause or suggestion. `POST /api/evaluations` `{complaint_id, usable, expert_cause?}`: `usable` is required; the cause is optional. Only the latest rating per person per complaint counts in `GET /api/evaluations` and in the dashboard target `summary_usable`. See `docs/SUMMARY_RATING.md`.

## Repeat complaints: decisions and review (FR-12, FR-13)
- `POST /api/complaints/check-repeat` applies the active repeat rule before saving and returns the linked earlier complaints (id, date, status, cause, why they matched).
- `POST /api/complaints` accepts `repeat_decisions: [{prior_complaint_id, decision: confirm|reject, reason?}]`. They are validated against the earlier complaints the rule links right now (an unlinked or repeated id is refused with `invalid_repeat_decision`, a dispute without a reason of at least 3 characters with `reason_required`) and stored in the same transaction as the complaint, next to the unchanged rule result. A confirmation without a reason is stored as "Confirmed by user".
- `POST /api/repeat-disputes` records a later decision. Only the person who registered the complaint (or an administrator) can decide, and only about a linked earlier complaint.
- `GET /api/repeat-disputes` lists decisions with who, when, both complaints, the reason, the rule version and the original evidence. `GET /api/export/disputes.csv` (analytics permission; the rule owner has it) exports the same for review.
- `python -m scripts.repeat_check --url ... --email ... [--save]` checks the eleven seeded scenarios and the decision round trip with a real account.

## Target field structure (FR-14)
`GET /api/field-mapping` returns the provisional mapping (23 mapped fields, 7 columns excluded with a reason, `one_to_one`, `validated: false`). `GET /api/complaints/{id}/target` returns a saved complaint with the target field names in the order of the field list, and `missing_required`. See `docs/FIELD_MAPPING.md`. `python -m scripts.requirements_check ... --save` checks it with a real account.

## Audit Trail (administrators and governance, `audit` permission)
`GET /api/audit/records?q=&include_seed=&page=&page_size=` lists every saved record: the PoC's own registrations newest first, then the synthetic history; `q` matches the record id, customer name or number. `GET /api/audit/records/{id}` returns one record in the target field structure, where each field came from (the field log written at save), the repeat check with the linked earlier complaints and the decisions on them, and the audit-log events about it. `GET /api/export/records.csv?include_seed=` exports the records with the target field names as columns; every export is written to the audit log (`records_exported`). In the app: the **Audit Trail** item in the left menu, directly under History.
