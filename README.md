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

## Accounts and sign-in

Employees create an account on the sign-in screen with their name, work e-mail, password and **function** (customer service, sales or site operations; TO CONFIRM with Renewi). A new account is **pending** until an administrator approves it on the **Users** screen; self-registered people are always employees and cannot choose a role. After sign-in each role lands on its own first screen and only sees the menu items it may use (employee: Register, History; team lead: Dashboard; evaluator: Evaluation; admin: Users and Configuration).

- Passwords are stored as salted scrypt hashes. Sign-in uses signed, expiring tokens (8 hours, kept in session storage); five wrong passwords lock the account for 15 minutes. Roles are read from the database on every request, and sign-ins, failures and role changes are in the audit trail.
- Settings are in `config.json` under `auth` (functions, approval on/off, allowed e-mail domains, password length, lockout).
- **First administrator (real account, no demo):** run this once in your own terminal. It asks for the password at a hidden prompt, so the password never appears on screen, in the shell history or in chat. It uses the database selected in `.env` (SQLite or Supabase).

  ```bash
  python -m backend.admin create-admin --email you@company.nl --name "Your Name"
  ```

  Then sign in on the sign-in screen. The admin lands on **Users**, where they approve people who signed themselves up, **add a person** (the app shows a one-time temporary password, which that person must change at first sign-in), **reset a password** (also unlocks the account), change roles, and disable accounts. Everyone can change their own password from the header; changing it ends all older sessions. If an admin is locked out, `python -m backend.admin set-password --email you@company.nl` sets a new password.
- **Demo accounts** (the ten fictional users, no password) are **off by default**. Set `POC_DEMO_MODE=1` only for a local demo; never in a shared deployment. The sign-in screen shows "Demo access" only while it is on.
- This is the PoC's own sign-in, not Renewi single sign-on. It is built so that the token check and login can be replaced by the client's identity provider (e.g. Microsoft Entra ID via OpenID Connect) without changing the screens or permissions. Password reset is done by an administrator (temporary password); there is no self-service e-mail reset yet because the PoC sends no e-mail.

## Customer data (customers, sites, contracts, orders, containers)

Customers, sites, contracts, orders and containers are synthetic and stand in for Renewi's own systems. For employees and admins the left menu has a **Customer data** group with five pages: **Customers, Sites, Contracts, Orders, Containers**.

- **Customers** lists every customer with how many sites, contracts, orders and containers each has (searchable, paged) and has **Add a customer**: the next customer number is assigned automatically and an optional first site makes the customer usable in the registration at once. **Open** jumps to that customer's sites.
- **Sites / Contracts / Orders / Containers** each list the rows of **all customers** with a customer column, a customer filter, a search box and paging, and have an **Add** form (in the all-customers view the form asks for the customer first). New rows appear in the registration dropdowns straight away; the half-filled complaint is kept, and **Review details** has a link here plus Sites/Contracts/Orders tables whose **Use** button fills the form.
- Everything added is marked **Added in the PoC** (with who and when) and audited. A contract, container or order must belong to the same site, container numbers are unique, and an order needs an existing container (add it first). Customers may share a name.
- In the real landscape this data would come from Renewi's systems and the PoC must never write to them; these pages only extend the PoC's own synthetic database. Containers are records of their own (migration 8).

## Supabase (Postgres)

By default the PoC uses the local SQLite file. To use a hosted Supabase database instead, put these in `.env` (never commit it): `POC_DB=postgres` and `DATABASE_URL=<Session pooler connection string, password URL-encoded>`. Choose an EU region. Restart the app; the schema is created and versioned automatically and the synthetic data is seeded only if the database is empty. `RESET=1 scripts/run_demo.sh` wipes and reseeds it.

- All tables have row-level security on with no policies, so Supabase's public REST API can read nothing; only the backend (connecting as the owner) can.
- `supabase/migrations/*.sql` are the same migrations as standard Supabase files, generated from `backend/migrations.py` (`python -m scripts.export_supabase_migrations`; add `--register` to record them in the project's migration history). A test fails if they drift from the code.
- Tests always run on SQLite. To run them on Postgres, set `POC_TEST_PG=1`; they then use a throwaway schema that is dropped afterwards. Browser tests are forced to SQLite.
- A hosted database adds network delay (about 0.25 s per query from a laptop).

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
