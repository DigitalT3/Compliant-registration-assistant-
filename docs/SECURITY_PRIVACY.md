# Security and Privacy

## PoC boundary

The application is synthetic-data-only. The FastAPI health and configuration responses identify the PoC mode, and complaint persistence in `backend/services/complaints.py` writes only to SQLite. No production complaint-system client or live write endpoint is implemented.

## Secrets and AI

`.env.example` contains only variable names and placeholders. Credentials must not be committed. The frontend does not receive AI provider secrets. Live AI mode is optional and unverified; no claim is made about EU hosting, DPIA completion, GDPR certification, or works-council approval.

## Access and logging

Demo users and backend permission checks model least-privilege roles for the demonstrator, but are not production authentication. The system records PoC audit, session, field, AI, and repeat evidence. Before any real-data phase, Renewi must approve data access, hosting, retention, access control, DPA arrangements, and governance controls.


## No write access to the live complaint system (FR-16)

The PoC has no client, address or credential for the live complaint system, so it cannot write to it (or read from it). The credentials that exist are only these:

| Credential | Belongs to | Reach |
|---|---|---|
| `DATABASE_URL` | the PoC's own Supabase project (or a local SQLite file when `POC_DB=sqlite`) | the PoC store: synthetic data and what testers register |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | an AWS IAM user for the language model (Bedrock) | invoking one model; refused on S3, DynamoDB, Secrets Manager and Lambda |
| `AUTH_SECRET`, account passwords | the PoC's own sign-in | the PoC only |

`python -m scripts.readonly_check` (and the tests in `tests/unit/test_readonly_guard_fr16.py`) check that nothing else appears: only known libraries, network code only in the database and AI modules, no complaint-system term, only localhost URLs, only the known environment keys (in the code, `.env.example` and `.env`), no secret in any tracked file or commit, no integration-style route, and no outbound connection during a full registration with the mock model. `--port 8001` also lists what a running app is connected to (it should be the PoC database, and Bedrock while a suggestion is made); `--aws` probes what the AWS identity is refused.

Limit: the PoC cannot read the IAM user's policy. In the AWS console, confirm that it allows only `bedrock:InvokeModel` on the one model in use. Delete the key when the PoC ends.
