# A clean database for the real user test

Why: the normal data now mixes the synthetic history with our own test complaints (POC-0001 and up), test accounts and test sessions. Those would skew the success measures: the share of "Other" causes in the test set, the repeat cases (the seeded repeat scenarios assume nobody has registered anything for those customers), and the averages on the dashboard.

What you get: a second set of tables (a schema, default name `usertest`) in the same Supabase project. It starts with only the synthetic customers and history, no test complaints, no sessions, no accounts but the administrator you create. The normal data (schema `public`) is not touched and stays as an archive.

## Start it
From the project folder:
```bash
scripts/run_usertest.sh
```
- **The first time** it creates the clean tables (about a minute: the hosted database is far away), asks for an administrator e-mail, name and password (hidden prompt), prints what the clean copy contains and starts the app on http://127.0.0.1:5173. It says "In this clean copy: 45 complaints (synthetic history), 0 sessions, 1 real accounts".
- **Every later time** it continues with the same clean copy. Nothing is reset.
- The usual `API_PORT=8001 scripts/run_demo.sh` keeps using the normal data. Which data you are on depends on which script you started, so check the printed "Clean copy: schema 'usertest'" line.

`CHECK_ONLY=1 scripts/run_usertest.sh` creates or checks the clean copy and stops without starting the app.

## Before the test
1. Sign in as the administrator and open **Users**. Create the testers (with their function), the team leads (with their team), and the evaluators (the PRD names Kwafie, Naomi and Maikel).
2. Record the stopwatch baseline on today's form (Evaluation screen, "Baseline").
3. Leave the clean copy alone until the test: do not register practice complaints in it. Practise in the normal data.

## Looking at the tables
In the Supabase Table Editor, switch the schema selector (top left of the table list) from `public` to `usertest`. The same tables are there.

## Start over (a second test day, or after a bad run)
Use another schema name; the previous one stays as a record:
```bash
POC_PG_SCHEMA=usertest2 scripts/run_usertest.sh
```
Removing a schema is a destructive step done by hand in Supabase (SQL editor: `DROP SCHEMA usertest CASCADE;`) and only when you are sure the results are saved (export the CSVs from the Dashboard first).

## Good to know
- The hosted database is about 190 ms away from a laptop in India, so timings in this copy still include that delay. For the timed sessions themselves, see `docs/LOCAL_SERVER.md` (a local database has no delay) or `docs/DEPLOY.md`.
- The AI model, the sign-in rules and everything else are the same as in the normal start.
