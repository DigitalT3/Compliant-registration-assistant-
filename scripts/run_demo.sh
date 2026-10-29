#!/usr/bin/env bash
# Start the PoC: fresh synthetic database, backend on :8000, frontend on :5173. Ctrl+C stops both.
# Override ports with API_PORT / WEB_PORT if 8000 or 5173 is taken.
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -c "import fastapi, uvicorn, pydantic, boto3" 2>/dev/null || .venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
[ -d frontend/node_modules ] || (cd frontend && npm install)

# SQLite: fresh synthetic data on every start. Postgres (POC_DB=postgres in .env): keep what is there and
# seed only if empty; run `RESET=1 scripts/run_demo.sh` to wipe and reseed the hosted database.
if grep -qiE '^POC_DB=(postgres|postgresql|supabase)' .env 2>/dev/null && [ -z "${RESET:-}" ]; then
  .venv/bin/python -m backend.seed --seed
else
  .venv/bin/python -m backend.seed --reset
fi
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd frontend
BACKEND_URL="http://127.0.0.1:$API_PORT" npx vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort
