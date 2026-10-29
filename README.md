# Renewi Complaint Registration Assistant PoC

This repository contains a standalone, desktop-first complaint-registration demonstrator for Renewi. It uses only deterministic synthetic data, stores records in a local SQLite PoC database, and does not connect to or write to Salesforce, Clear, mailboxes, or any other Renewi production system.

## Implemented scope

The React/Vite frontend provides a Dutch and English six-step workflow: customer lookup (customer number, order, container, name or postcode, or a pasted email), detail review, complaint description, one AI analysis call (summary, type and top-three causes), repeat checking with confirm/dispute, and PoC-only save. The FastAPI backend provides synthetic lookup and context, configurable per-type defaults with provenance, a two-level root-cause taxonomy, deterministic repeat detection, complaint persistence, session events, audit events, demo roles, and OpenAPI documentation.

For the user test it also records test sessions (participant, scenario, assistant or plain-form mode), baseline stopwatch timings, exit interviews and blind expert labelling, and the dashboard evaluates each PRD target with its sample size and exports CSV.

AI behaviour is mock by default. The mock provider is explicitly labelled in the UI and API; it is deterministic and intended for offline demonstration, not as evidence of live-model quality.

## Prerequisites

Use Python 3.12 or a compatible Python 3 release, plus Node.js 18 or later with npm. Install Python dependencies from `requirements.txt` and frontend dependencies from `frontend/package.json`.

## Setup and run

One command (creates the venv, installs dependencies, resets the synthetic data, starts both servers; use `API_PORT` / `WEB_PORT` if 8000 or 5173 is taken):

```bash
scripts/run_demo.sh
```

Or step by step. From the project root, create a local environment and install backend dependencies.

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

`config.json` is the central source for the provisional taxonomy, complaint-type channel defaults, required fields, synthetic users, fixed clock, and repeat rule. The active default repeat rule matches the same customer and site, matches at root-cause category level (level one; switchable to level two in Configuration), considers `open` and `closed` historical complaints, and uses an inclusive 60-day lookback. These values are provisional and require Renewi confirmation.

Copy `.env.example` to `.env` for local settings. `AI_PROVIDER=mock` is the safe default. Live OpenAI-compatible mode requires an approved endpoint and credentials through `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY`; it was not verified because no credentials were supplied.

## Tests

Run backend tests from the project root.

```bash
python -m pytest -q
```

Run the frontend build and the browser scripted cases from `frontend/`. The browser tests use the Google Chrome installed on the machine and start their own backend (port 8010) and frontend (port 5183) on a fresh synthetic database, so they do not touch a running demo.

```bash
npm run build
npm run test:e2e
```

Latest recorded run: 61 Python tests passed, 14 Chromium scripted cases passed (T01-T10 plus email, plain-form, dashboard and Dutch UI), TypeScript check and production build passed. These are separate runs. See `docs/TEST_RESULTS.md` for qualifications.

## Limitations

This is not production authentication, production security certification, GDPR approval, or a real-data evaluation. Live AI, real-user acceptance, current-process timing comparisons, expert-label agreement, and historical taxonomy analysis remain unverified. See the handover documents in `docs/` for requirements traceability, known issues, open questions, API details, and the demo script.
