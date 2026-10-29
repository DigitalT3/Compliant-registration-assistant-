#!/usr/bin/env bash
# Start the PoC on a CLEAN copy of the data for the real user test, in the same Supabase project.
#
# The clean copy is its own schema (set of tables, default name "usertest"): synthetic history only, no test
# complaints, no test accounts. The data in the normal schema (public) is not touched and stays as an archive.
#
#   scripts/run_usertest.sh                       # start (creates the clean schema the first time, asks for an administrator)
#   POC_PG_SCHEMA=usertest2 scripts/run_usertest.sh   # another clean copy (for example a second test day)
#   CHECK_ONLY=1 scripts/run_usertest.sh          # create/check the clean copy and stop (no servers)
#
# The usual start (scripts/run_demo.sh without this) keeps using the normal data. API_PORT and WEB_PORT work as there.
# Nothing here resets anything: running it again continues with the same clean copy. To start over, use another schema name.
set -euo pipefail
cd "$(dirname "$0")/.."

SCHEMA="${POC_PG_SCHEMA:-usertest}"
if ! [[ "$SCHEMA" =~ ^[a-z_][a-z0-9_]*$ ]] || [ "$SCHEMA" = "public" ]; then
  echo "POC_PG_SCHEMA must be a simple lowercase name that is not 'public' (got '$SCHEMA')." >&2
  exit 1
fi
if ! grep -qiE '^POC_DB=(postgres|postgresql|supabase)' .env 2>/dev/null; then
  echo ".env does not select the hosted database (POC_DB=postgres). Nothing to make a clean copy of." >&2
  exit 1
fi
export POC_PG_SCHEMA="$SCHEMA"
export POC_DEMO_MODE=0
PY=.venv/bin/python

[ -d .venv ] || python3 -m venv .venv
$PY -c "import fastapi, uvicorn, pydantic, boto3" 2>/dev/null || .venv/bin/pip install -q -r requirements.txt

echo "Clean copy: schema '$SCHEMA' in the hosted database (the normal data in 'public' is not touched)."
# Create the tables and the synthetic customers and history only when the schema is new. This is not a reset.
$PY -m backend.seed --seed >/dev/null

HAS_ADMIN=$($PY - <<'PYEOF'
from backend import db
with db.connect() as c:
    print(c.execute("SELECT count(*) FROM users WHERE role='admin' AND status='active' AND email IS NOT NULL").fetchone()[0])
PYEOF
)
if [ "$HAS_ADMIN" = "0" ]; then
  echo "This clean copy has no administrator yet."
  [ -n "${ADMIN_EMAIL:-}" ] || read -r -p "Administrator e-mail: " ADMIN_EMAIL
  [ -n "${ADMIN_NAME:-}" ] || read -r -p "Administrator name: " ADMIN_NAME
  $PY -m backend.admin create-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

$PY - <<'PYEOF'
from backend import db
with db.connect() as c:
    n = lambda sql: c.execute(sql).fetchone()[0]
    print(f"In this clean copy: {n('SELECT count(*) FROM complaints')} complaints (synthetic history), "
          f"{n('SELECT count(*) FROM sessions')} sessions, {n('SELECT count(*) FROM users WHERE email IS NOT NULL')} real accounts, "
          f"{n('SELECT count(*) FROM baseline')} baseline rows, {n('SELECT count(*) FROM evaluations')} labels.")
PYEOF

if [ "${CHECK_ONLY:-}" = "1" ]; then exit 0; fi
echo "Starting. Open http://127.0.0.1:${WEB_PORT:-5173} and sign in with the administrator of this clean copy."
exec scripts/run_demo.sh
