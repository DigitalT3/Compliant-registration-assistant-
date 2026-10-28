# Security and Privacy

## PoC boundary

The application is synthetic-data-only. The FastAPI health and configuration responses identify the PoC mode, and complaint persistence in `backend/services/complaints.py` writes only to SQLite. No production complaint-system client or live write endpoint is implemented.

## Secrets and AI

`.env.example` contains only variable names and placeholders. Credentials must not be committed. The frontend does not receive AI provider secrets. Live AI mode is optional and unverified; no claim is made about EU hosting, DPIA completion, GDPR certification, or works-council approval.

## Access and logging

Demo users and backend permission checks model least-privilege roles for the demonstrator, but are not production authentication. The system records PoC audit, session, field, AI, and repeat evidence. Before any real-data phase, Renewi must approve data access, hosting, retention, access control, DPA arrangements, and governance controls.
