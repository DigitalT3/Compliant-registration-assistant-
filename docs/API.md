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
