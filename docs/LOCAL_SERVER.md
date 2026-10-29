# Running the PoC on one computer for timed sessions

Why: a hosted database costs about 180 ms per call from a laptop, which adds roughly 10 to 15 seconds of waiting to every registration. With a local database the wait is 0 ms, so the timings show the app and not the network. See `docs/DEPLOY.md` for the alternative (hosting next to the database).

What you get: one address that serves the pages and the API, a local database file that is never reset, real accounts (demo accounts are off), and the real AI model if `.env` has the AWS settings.

What you give up: the records live in a local file, not in Supabase, and testers must reach this computer.

## Start (every time)
From the project folder:
```bash
scripts/run_local_server.sh
```
- **The first time** it builds the pages, creates the database file `data/timed-test.sqlite3` with the synthetic customers, and asks for an administrator e-mail, name and password (typed at a hidden prompt).
- **Every later time** it only starts the server. Nothing is deleted or reset.
- It prints the addresses: `http://localhost:8080` on this computer and `http://<address>:8080` for anyone on the same network.
- Stop with **Ctrl+C**. Leave the Terminal open while testers work. The script keeps the Mac awake; keep it plugged in and do not close the lid.

On the first start macOS may ask whether Python may accept incoming connections. Choose **Allow**, or testers on other computers cannot connect.

## Before the session
1. Sign in as the administrator and open **Users**. Create the testers, the team leads (with their team) and the evaluator. Give each person their temporary password; they choose their own at first sign-in.
2. Check the speed: `POC_DB=sqlite POC_DB_PATH=data/timed-test.sqlite3 .venv/bin/python -m scripts.db_latency` should print about 0 ms.
3. For testers who are not on the same network, use the free tunnel (below).

## Testers who are somewhere else
Install Cloudflare's tunnel tool once (`brew install cloudflared`), then start with:
```bash
TUNNEL=1 scripts/run_local_server.sh
```
It prints a temporary public address (`https://….trycloudflare.com`). It changes every time and stops when you stop the script. Anyone with the address can reach the sign-in page, so keep demo accounts off (they are), use strong passwords, and use synthetic data only.

## During and after the session
- **Watch the data:** the Dashboard, History and Users screens read the same file. To look at the tables themselves, open `data/timed-test.sqlite3` with DB Browser for SQLite (free) or `sqlite3 -header -column data/timed-test.sqlite3 "SELECT * FROM complaints ORDER BY created DESC LIMIT 5;"`. Refresh to see new rows.
- **Keep the results:** copy the file (`cp data/timed-test.sqlite3 data/timed-test-DATE.sqlite3`) and download the CSVs from the Dashboard (`sessions.csv`, `suggestions.csv`).
- **Start again from nothing:** stop the server and move or delete the file. The next start creates a new one and asks for a new administrator.

## Options
| Setting | Meaning |
|---|---|
| `PORT=8081` | Use another port when 8080 is taken |
| `POC_DB_PATH=data/other.sqlite3` | Use a different database file, for example one per session day |
| `MOCK_AI=1` | Use the labelled mock instead of the real model (no AWS call, no cost) |
| `TUNNEL=1` | Also open the temporary public address |
| `ADMIN_EMAIL`, `ADMIN_NAME`, `POC_ADMIN_PASSWORD` | Create the first administrator without prompts (a password in a variable is visible to other programs on the computer; use it only on your own machine) |

## Things to know
- The hosted Supabase database is not touched: the script sets the local database for this run only, whatever `.env` says.
- The AI call still goes to AWS (2 to 4 seconds), so that part of the time is real and stays in the result.
- Records are not in Supabase. If you want them there afterwards, a copy script would have to be written.
- This is a demonstrator on a laptop: no backups unless you make them, and no protection if the laptop is lost. Use synthetic data only.
