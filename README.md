# Renewi Complaint Registration Assistant PoC

This repository contains a standalone, desktop-first complaint-registration demonstrator for Renewi. It uses only deterministic synthetic data, stores records in a local SQLite PoC database, and does not connect to or write to Salesforce, Clear, mailboxes, or any other Renewi production system.

## Implemented scope

The React/Vite frontend provides a Dutch and English six-step workflow for customer lookup, detail review, complaint description, summary, classification, repeat checking, and PoC-only save. The FastAPI backend provides synthetic lookup and context, configurable defaults with provenance, deterministic repeat detection, complaint persistence, session events, audit events, dashboard metrics, demo roles, and OpenAPI documentation.

AI behaviour is mock by default. The mock provider is explicitly labelled in the UI and API; it is deterministic and intended for offline demonstration, not as evidence of live-model quality.

## Prerequisites

Use Python 3.12 or a compatible Python 3 release, plus Node.js 18 or later with npm. Install Python dependencies from `requirements.txt` and frontend dependencies from `frontend/package.json`.

## Setup and run

From the project root, create a local environment and install backend dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m backend.seed --reset
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend.

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. The API health response is at `http://127.0.0.1:8000/health`; FastAPI generates API documentation at `http://127.0.0.1:8000/docs`.

## Synthetic data and reset

`python -m backend.seed --reset` destructively recreates the local PoC tables and loads the fixed synthetic dataset. `python -m backend.seed --fingerprint` reports table counts and a deterministic content hash. The default fixed seed anchor keeps scripted repeat scenarios stable; do not use the data as real Renewi customer or complaint data.

## Configuration

`config.json` is the central source for the provisional taxonomy, complaint-type channel defaults, required fields, synthetic users, fixed clock, and repeat rule. The active default repeat rule matches the same customer and site, uses level-two root-cause matching, considers `open` and `closed` historical complaints, and uses an inclusive 60-day lookback. These values are provisional and require Renewi confirmation.

Copy `.env.example` to `.env` for local settings. `AI_PROVIDER=mock` is the safe default. Live OpenAI-compatible mode requires an approved endpoint and credentials through `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY`; it was not verified because no credentials were supplied.

## Tests

Run backend tests from the project root.

```bash
python -m pytest -q
```

Run the frontend build and browser journey from `frontend/`.

```bash
npm run build
npm run test:e2e
```

The recorded results are 24 Python tests passed in 15.17 seconds, one Chromium Playwright journey passed in 5.1 seconds, and the production frontend build passed in 1.26 seconds. These are separate runs, not a single combined execution. See `docs/TEST_RESULTS.md` for qualifications.

## Limitations

This is not production authentication, production security certification, GDPR approval, or a real-data evaluation. Live AI, real-user acceptance, current-process timing comparisons, expert-label agreement, and historical taxonomy analysis remain unverified. See the handover documents in `docs/` for requirements traceability, known issues, open questions, API details, and the demo script.
