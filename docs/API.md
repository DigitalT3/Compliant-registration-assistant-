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
| `GET /api/analytics/summary`, `/sessions` | Recorded metrics and session records; requires `analytics`. |
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
| `POST /api/users` | `users` (admin) | `{name, email, function?, role}`; creates an active account and returns a one-time `temporary_password` (must be changed at first sign-in) |
| `POST /api/users/{id}/reset-password` | `users` (admin) | New one-time temporary password; unlocks the account |
| `GET /api/users?status=` | `users` (admin) | List accounts, pending first |
| `PATCH /api/users/{id}` | `users` (admin) | `{status, role, user_group}`; the last active admin cannot be disabled or demoted, and nobody can disable themselves |

Send `Authorization: Bearer <token>`. While a temporary password is in use, every endpoint except `/api/auth/me`, `/api/auth/change-password`, `/api/auth/logout` and `/api/auth/options` answers 403 `password_change_required`. The `X-Demo-User` header is accepted only while `POC_DEMO_MODE=1`.
