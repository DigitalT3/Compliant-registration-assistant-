# Hosting the PoC next to the database (Fly.io, Paris)

Why: from a laptop every database call takes about 180 ms, so timed sessions include a lot of network delay that today's form does not have. Running the backend in the same region as Supabase (Paris, `eu-west-3`) brings a call down to a few milliseconds. One server then serves the pages and the API, and every tester just opens a web address.

What this does not change: the AI call (2 to 4 seconds) and the delay between a tester's browser and the server (one trip per click).

The hosting files are in the repository: `Dockerfile`, `fly.toml`, `.dockerignore`. The backend serves the built front end when `SERVE_FRONTEND=1` (already set in `fly.toml`). Nothing secret is in these files.

## Before you start
- A Fly.io account (it may ask for a payment card; an always-on small machine costs a few dollars per month, check Fly's current prices). Sign up at fly.io.
- Fly's command line tool `fly` (also called `flyctl`). On a Mac with Homebrew: `brew install flyctl`. If it is already installed, `fly version` works.
- The project's `.env` on your computer, with the real `DATABASE_URL` and the AWS values. They are sent to the host as secrets and never end up in the image or in git.
- This is a demonstrator with synthetic data. The page is on the public internet: sign-in is required (demo accounts are off) and new accounts wait for an administrator's approval.

## Steps (about 15 minutes)

1. **Sign in to Fly**
   ```bash
   fly auth login
   ```

2. **Choose a name nobody else uses and create the app.** Replace `YOUR-APP` everywhere below (for example `renewi-poc-anna`).
   ```bash
   fly apps create YOUR-APP
   ```
   Then edit the first line of `fly.toml` so that `app = "YOUR-APP"`.

3. **Send the secrets to the host.** This copies only the database and AI settings from your `.env`; the values are not printed.
   ```bash
   grep -E '^(DATABASE_URL|LLM_PROVIDER|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_REGION|BEDROCK_MODEL_ID)=' .env | fly secrets import -a YOUR-APP
   ```
   Check the names (not the values) with `fly secrets list -a YOUR-APP`: you should see those six.

4. **Deploy.** Fly builds the container on its own build machine, so you do not need Docker.
   ```bash
   fly deploy -a YOUR-APP
   ```
   The first build takes a few minutes.

5. **Keep one machine.** The app keeps some settings in memory, so use a single machine.
   ```bash
   fly scale count 1 -a YOUR-APP
   ```

6. **Open it.** The address is `https://YOUR-APP.fly.dev`. Sign in with your real admin account. The accounts and data are the same as before, because the database is the same Supabase project.

## Check that it works and is faster
```bash
curl https://YOUR-APP.fly.dev/health
```
It should say `"status":"ok"`, `"ai_mock":false` and `"ai_region"`.

Compare the database round trip from your laptop and from the host:
```bash
python -m scripts.db_latency
fly ssh console -a YOUR-APP -C "python -m scripts.db_latency"
```
From the laptop it is about 180 ms; from the host it should be a few milliseconds. Register a complaint on the hosted address and look at the step times on the dashboard: they should be much shorter than before.

## Everyday use
- **Update after a change:** commit, then `fly deploy -a YOUR-APP` again.
- **Logs when something is wrong:** `fly logs -a YOUR-APP`.
- **Pause to stop the cost:** `fly scale count 0 -a YOUR-APP`; resume with `fly scale count 1 -a YOUR-APP`.
- **Remove everything:** `fly apps destroy YOUR-APP`.
- **Change a secret** (for example new AWS keys): run step 3 again, or `fly secrets set NAME=value -a YOUR-APP`.

## Things to watch
- **EU hosting of the AI:** the host being in Paris does not change where the AI model runs. The AI region is set by `AWS_REGION` and `BEDROCK_MODEL_ID`; for the PRD's EU requirement use an EU region and an `eu.` inference profile.
- **Who can reach it:** anyone can open the sign-in page. Self-registered people cannot do anything until an administrator approves them. To accept only company addresses, list the domains under `auth.allowed_email_domains` in `config.json`.
- **AWS keys:** give them only the permission to call the model (Bedrock invoke), and replace them if they were ever shared.
- **Not production:** one machine, no backups beyond Supabase's own, no monitoring. It is meant for the timed sessions.
- **The first deploy is untested here:** the image was not built on the author's computer (no Docker there). If the build or the start fails, `fly logs` shows why; send that output.
