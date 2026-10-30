# Renewi Complaint Registration Assistant PoC

This repository contains a standalone, desktop-first complaint-registration demonstrator for Renewi. It uses only deterministic synthetic data, stores records in a local SQLite PoC database, and does not connect to or write to Salesforce, Clear, mailboxes, or any other Renewi production system.

## Implemented scope

The PoC stays inside PRD section 6 (what is in and out of scope): see [docs/SCOPE.md](docs/SCOPE.md), which is partly enforced by `tests/unit/test_scope_guard.py`.

The React/Vite frontend provides a Dutch and English six-step workflow: customer lookup (customer number, order, container, name or postcode, or a pasted email), detail review, complaint description, one AI analysis call (summary, type and top-three causes), repeat checking with confirm/dispute, and PoC-only save. The FastAPI backend provides synthetic lookup and context, configurable per-type defaults with provenance, a two-level root-cause taxonomy, deterministic repeat detection, complaint persistence, session events, audit events, demo roles, and OpenAPI documentation.

For the user test it also records test sessions (participant, scenario, assistant or plain-form mode), baseline stopwatch timings, exit interviews and blind expert labelling, and the dashboard evaluates each PRD target with its sample size and exports CSV (per-session timings and `suggestions.csv`, one row per field with accepted / changed / typed / empty, for Power BI). A team lead's account carries the team they lead and sees only that team on the dashboard and in the exports; admins and evaluators see all teams. Step times count at most 10 minutes per visit (`metrics.step_idle_cap_seconds`; repeated visits add up) and the dashboard shows the mean and the median per step. The registration clock starts when the form is opened (not when the customer is chosen), and the dashboard shows the median time to the first field filled and to the first field the employee entered themselves. Sessions recorded before this change started at the customer choice, so their first-field time is shorter.

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

Employees create an account on the sign-in screen with their name, work e-mail, password and **function** (customer service, sales or site operations; TO CONFIRM with Renewi). A new account is **pending** until an administrator approves it on the **Users** screen; self-registered people are always employees and cannot choose a role. After sign-in each role lands on its own first screen and only sees the menu items it may use (employee: Register, History; team lead: Dashboard, limited to the team they lead; evaluator: Evaluation; admin: Users and Configuration).

- Passwords are stored as salted scrypt hashes. Sign-in uses signed, expiring tokens (8 hours, kept in session storage); five wrong passwords lock the account for 15 minutes. Roles are read from the database on every request, and sign-ins, failures and role changes are in the audit trail.
- Settings are in `config.json` under `auth` (functions, approval on/off, allowed e-mail domains, password length, lockout).
- **First administrator (real account, no demo):** run this once in your own terminal. It asks for the password at a hidden prompt, so the password never appears on screen, in the shell history or in chat. It uses the database selected in `.env` (SQLite or Supabase).

  ```bash
  python -m backend.admin create-admin --email you@company.nl --name "Your Name"
  ```

  Then sign in on the sign-in screen. The admin lands on **Users**, where they approve people who signed themselves up, **add a person** (the app shows a one-time temporary password, which that person must change at first sign-in), **reset a password** (also unlocks the account), change roles, and disable accounts. Everyone can change their own password from the header; changing it ends all older sessions. If an admin is locked out, `python -m backend.admin set-password --email you@company.nl` sets a new password.
- **Demo accounts** (the ten fictional users, no password) are **off by default**. Set `POC_DEMO_MODE=1` only for a local demo; never in a shared deployment. The sign-in screen shows "Demo access" only while it is on.
- This is the PoC's own sign-in, not Renewi single sign-on. It is built so that the token check and login can be replaced by the client's identity provider (e.g. Microsoft Entra ID via OpenID Connect) without changing the screens or permissions. Password reset is done by an administrator (temporary password); there is no self-service e-mail reset yet because the PoC sends no e-mail.

## Defaults on Review details

FR-04: after a match the customer, site, contract, order, container, channel, registration date and registering user are all filled, and each one can be edited (customer through *Change customer*). When the search points at no site, the site of the customer's latest order is used, and the contract and order follow it. The step opens with as much filled in as is knowable (PRD step 2). The channel follows how the complaint arrived: **phone** when the employee searched (the customer is on the phone) and **email** when started from a pasted email (`origin_defaults` in `config.json`, TO CONFIRM). Priority and status default for every type. The owner team and response target depend on the complaint type, so **Complaint type** is the first field on the step and is highlighted until chosen; for an email the type is guessed from the text and shown as *Suggested*, so everything is already filled. Values the employee typed are never overwritten, and each field shows where its value came from.

## Customer data (customers, sites, contracts, orders, containers)

Customers, sites, contracts, orders and containers are synthetic and stand in for Renewi's own systems. For employees and admins the left menu has a **Customer data** group with five pages: **Customers, Sites, Contracts, Orders, Containers**.

- **Customers** lists every customer with how many sites, contracts, orders and containers each has (searchable, paged) and has **Add a customer**: the next customer number is assigned automatically and an optional first site makes the customer usable in the registration at once. **Open** jumps to that customer's sites.
- **Sites / Contracts / Orders / Containers** each list the rows of **all customers** with a customer column, a customer filter, a search box and paging, and have an **Add** form (in the all-customers view the form asks for the customer first). New rows appear in the registration dropdowns straight away, and the half-filled complaint is kept while you are on these pages. **Review details** keeps its own Sites / Contracts / Orders tables whose **Use** button fills the form.
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

**Claude on Amazon Bedrock** (`LLM_PROVIDER=bedrock`, wins over `AI_PROVIDER`): set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` and `BEDROCK_MODEL_ID` in `.env` (keys stay out of git), restart the backend, then run `python -m scripts.live_ai_check`. Verified once against Bedrock in `us-east-2` (6/6 valid answers, about 3-5 s each). For the PRD's EU-hosting requirement use an EU region (e.g. `eu-central-1`) and an `eu.` inference profile; `/health` shows `ai_region`. Tests never call a real model.

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

## Field profile (time sink 2: many fields, few defaults)

`scripts/field_profile.py` shows, for every field, how often it is filled, how many different values it has, the most common value and its share, and flags a field as a **default candidate** when one value covers at least 80 % of the filled records. It runs outside the app and changes nothing.

```bash
# Renewi's complaint history: one row per complaint, one column per field, one date column
python -m scripts.field_profile --csv export.csv --date-column created --months 12 --out profile.csv

# the PoC's own complaints (synthetic history and registrations made in the app)
python -m scripts.field_profile --poc [--source poc|seed|all]
```

The export can use commas, semicolons or tabs. `--months 12` keeps the last twelve months (counted back from the newest complaint) and warns when the data covers less. Empty cells and placeholders such as `n/a`, `null` and `-` count as not filled. Free-text and personal-detail columns (description, name, e-mail, reason, notes and any long value) and identifier columns are never given a default candidate and their values are never printed, so the report can be shared. A candidate is only a starting point: the process owner decides whether the common value is the right default. On the PoC's synthetic history (about 5 months) it is a demonstration, not evidence about today's form.

## Hosting next to the database

From a laptop each database call takes about 180 ms, which inflates timed sessions. `docs/DEPLOY.md` explains how to run the backend (which then also serves the built front end) on Fly.io in Paris, next to the Supabase project, with the secrets set on the host. `python -m scripts.db_latency` measures the round trip from wherever it runs.

## Running on one computer for timed sessions

`scripts/run_local_server.sh` runs the whole PoC on a local database (no network delay), serves the pages and the API from one address and never resets data. See `docs/LOCAL_SERVER.md` for the first start, adding testers, a free tunnel for remote testers, and keeping the results.

## A clean database for the real user test

`scripts/run_usertest.sh` starts the PoC on a clean schema in the same Supabase project (synthetic history only, no test complaints or accounts) so the test set is not mixed with our own testing; the normal data stays untouched. See `docs/USER_TEST_DATABASE.md`.


## Team lead: how each person registers

The dashboard has a **By employee** table (and `employees.csv`): per person the saved and started registrations, the median time with its spread, how often the assistant's summary and cause were kept unchanged, the top-3 share, the "Other" share, the prefill rate and the repeat decisions, next to a "Whole team" row. A team lead sees only the people of their own team; admins and evaluators see every team. A share that rests on fewer than 3 registrations is hidden (`report.per_employee_min_n`), so nobody is judged on one or two cases. The view works with real accounts and real sign-in; people appear under the name of their account.

## Rule sign-off and the go/no-go readout

**Repeat rule (rule owner).** Accounts with the role `rule_owner` (Juul at Renewi) can edit the repeat rule and **sign it off** or **request changes** on the Configuration page, next to the employees' disputes. A sign-off belongs to the exact rule parameters (lookback, match keys, cause mode, statuses, missing values): editing the rule makes it a draft again and earlier sign-offs stay as history. Once signed off, the note on the Check and save step says who signed it off and when, instead of "provisional". Administrators can still edit but cannot sign off for the owner. Audit actions: `repeat_rule_signed_off`, `repeat_rule_changes_requested`.

**Readout (business owner).** Accounts with the role `business_owner` (Glenn) get a **Readout** page: the PRD targets with sample sizes, the baseline comparison, the open conditions (cause list agreed, rule signed off, enough registrations, labels and exit interviews, a timed baseline) and an export. The page does not compute a verdict. The business owner records **go**, **go with conditions** or **no-go** with a reason; it is stored with the evidence it was based on and in the audit log (`go_no_go_decision`). Evaluators and administrators can read the page but cannot decide.

## Agreeing the root-cause list ("agree v1")

The cause list is a draft until the process owners agree to it. On the **Root causes** page each person with the evaluator role can **agree** or **request changes** (a comment is required); the page shows who agreed, when, and the state: *Draft*, *Changes requested* or *Agreed* (at least `taxonomy_review.required_agreements` people, 3 by default, and no open request for changes). A review belongs to one exact version of the list: when a cause, name, definition or example changes, earlier agreements stay as history but no longer count. The state is also shown on the About page and as a note on the Classify step while the list is not agreed. Every review is written to the audit log (`taxonomy_agreed`, `taxonomy_changes_requested`). Administrators can read the page but cannot agree on the owners' behalf.
