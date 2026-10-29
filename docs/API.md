# API Reference

## Access and errors

The API is served by FastAPI. Generated OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`. Protected routes use the PoC-only `X-Demo-User` header. Errors use `{ "error": { "code", "message", "request_id" } }`.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | PoC, synthetic-data, clock, and AI-mode status. |
| `GET /api/config`, `/defaults`, `/root-causes`, `/repeat-rule` | Effective non-secret configuration and provisional metadata. |
| `PUT /api/config/repeat-rule`, `/defaults` | Update configuration; requires `configure`. |
| `GET /api/customers/search?q=` | Search by customer number, order, container, or name. |
| `GET /api/customers/{id}` and `/{id}/context` | Customer, site, contract, and order context. |
| `POST /api/prefill` | Editable prefill and provenance. |
| `POST /api/complaints/extract`, `/summarise`, `/classify`, `/check-repeat` | AI-assisted extraction, summary, classification, and deterministic repeat check. |
| `POST /api/complaints`; `GET /api/complaints`; `GET /api/complaints/{id}` | PoC-only complaint persistence, history, and detail. |
| `POST /api/sessions`, `/api/sessions/{id}/events`, `/complete` | Session and event recording. |
| `GET /api/analytics/summary`, `/sessions` | Recorded metrics and session records; requires `analytics`. A **team lead** only gets the team they lead (a `group` in the request is ignored; the summary carries `scope.team`); a lead without a team gets 403 `team_required`. Admins and evaluators get every team. Each step counts at most `metrics.step_idle_cap_seconds` (600) per visit. |
| `GET /api/export/sessions.csv`, `/suggestions.csv` | Per-session timings; and one row per tracked field of every saved complaint (`team`, `field`, `origin`, `outcome` = accepted / changed / typed / empty) for Power BI. Same team scoping as the dashboard. |
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
