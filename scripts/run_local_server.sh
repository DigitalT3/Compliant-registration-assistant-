#!/usr/bin/env bash
# Run the whole PoC on this computer with a LOCAL database (SQLite), for timed sessions without network delay.
# One address serves the pages and the API. It never resets data: stop it and start it again and everything is still there.
#
#   scripts/run_local_server.sh                  # testers on the same network open http://<this computer>:8080
#   TUNNEL=1 scripts/run_local_server.sh         # also opens a free temporary public address (needs `cloudflared`)
#   MOCK_AI=1 scripts/run_local_server.sh        # use the labelled mock instead of the real model
#
# Settings: PORT (default 8080), POC_DB_PATH (default data/timed-test.sqlite3). For the first administrator you can
# set ADMIN_EMAIL, ADMIN_NAME and POC_ADMIN_PASSWORD instead of answering the prompts. Ctrl+C stops everything.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8080}"
export POC_DB=sqlite                                  # the shell wins over .env, so the hosted database is not touched
export POC_DB_PATH="${POC_DB_PATH:-data/timed-test.sqlite3}"
export SERVE_FRONTEND=1
export POC_DEMO_MODE=0
if [ "${MOCK_AI:-}" = "1" ]; then export LLM_PROVIDER=mock AI_PROVIDER=mock; fi
PY=.venv/bin/python

if lsof -ti ":$PORT" >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop that program or start with PORT=8081 scripts/run_local_server.sh" >&2
  exit 1
fi

[ -d .venv ] || python3 -m venv .venv
$PY -c "import fastapi, uvicorn, pydantic, boto3" 2>/dev/null || .venv/bin/pip install -q -r requirements.txt

# Build the pages when they are missing or older than the source.
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  [ -d frontend/node_modules ] || (cd frontend && npm install)
  (cd frontend && npm run build)
fi

# Create the schema and the synthetic customers only when the file is new. This is not a reset.
mkdir -p "$(dirname "$POC_DB_PATH")"
$PY -m backend.seed --seed

# The first administrator (typed at a hidden prompt) when the database has none.
HAS_ADMIN=$($PY - <<'PYEOF'
from backend import db
with db.connect() as c:
    print(c.execute("SELECT count(*) FROM users WHERE role='admin' AND status='active' AND email IS NOT NULL").fetchone()[0])
PYEOF
)
if [ "$HAS_ADMIN" = "0" ]; then
  echo "This database has no administrator yet."
  [ -n "${ADMIN_EMAIL:-}" ] || read -r -p "Administrator e-mail: " ADMIN_EMAIL
  [ -n "${ADMIN_NAME:-}" ] || read -r -p "Administrator name: " ADMIN_NAME
  $PY -m backend.admin create-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
echo
echo "Database file: $POC_DB_PATH   (back it up; it holds all records)"
echo "This computer:           http://localhost:$PORT"
[ -z "$IP" ] || echo "Same network:            http://$IP:$PORT"

TUNNEL_PID=""
cleanup() { [ -z "$TUNNEL_PID" ] || kill "$TUNNEL_PID" 2>/dev/null || true; }
trap cleanup EXIT
if [ "${TUNNEL:-}" = "1" ]; then
  if command -v cloudflared >/dev/null 2>&1; then
    LOG="$(mktemp)"
    cloudflared tunnel --url "http://localhost:$PORT" >"$LOG" 2>&1 &
    TUNNEL_PID=$!
    for _ in $(seq 1 30); do
      URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)"
      [ -z "$URL" ] || break
      sleep 1
    done
    echo "Public (temporary):      ${URL:-not ready; see $LOG}"
    echo "Anyone with this address can reach the sign-in page. Keep demo accounts off and use strong passwords."
  else
    echo "TUNNEL=1 needs cloudflared. Install it with: brew install cloudflared" >&2
  fi
fi
echo "Stop with Ctrl+C."
echo

# caffeinate keeps the computer awake while the server runs
exec_cmd=("$PY" -m uvicorn backend.app:app --host 0.0.0.0 --port "$PORT")
if command -v caffeinate >/dev/null 2>&1; then caffeinate -i "${exec_cmd[@]}"; else "${exec_cmd[@]}"; fi
