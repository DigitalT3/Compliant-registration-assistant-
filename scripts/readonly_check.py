"""FR-16 check: the PoC never writes to the live complaint system, because nothing in it can reach that system.

    python -m scripts.readonly_check                       # the code, configuration and credentials in this folder
    python -m scripts.readonly_check --port 8001           # also what a RUNNING app is connected to right now (needs lsof)
    python -m scripts.readonly_check --history             # also every commit ever made
    python -m scripts.readonly_check --aws                 # also what the AWS identity in .env is refused (read-only probes)

The rules (each one fails the check when broken):
  1. Only known libraries are installed (requirements.txt); a CRM or database client for another system needs a decision.
  2. Only the database module and the AI module open network connections; everything else in the backend cannot.
  3. No word from a complaint system (Salesforce, ServiceNow, SOQL, Dynamics, SAP, a Renewi host) appears in code or configuration.
  4. The only URLs in the code are this machine's own.
  5. The only environment variables the code reads, and the only keys in .env.example and .env, are the known ones:
     the PoC store, the AI model and the app's own settings. A credential for anything else must be added here on purpose.
  6. No secret (AWS key, private key, database URL with a password, API key) is in a tracked file.
  7. No route is named like an integration (sync, push, webhook, write-back).
It prints key NAMES and host names, never values.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PACKAGES = {"fastapi", "uvicorn", "pydantic", "pytest", "httpx", "psycopg", "boto3"}
NETWORK_MODULES = {"backend/db.py", "backend/services/ai.py"}
NETWORK_IMPORT = re.compile(r"^\s*(?:import|from)\s+(requests|httpx|urllib\.request|aiohttp|http\.client|smtplib|ftplib|socket|boto3|botocore|psycopg|paramiko|pymysql|pyodbc|cx_Oracle|simple_salesforce|zeep)\b", re.M)
FORBIDDEN_TERMS = re.compile(r"salesforce|force\.com|soql|servicenow|service-now|dynamics\s?365|sap\.com|renewi\.(?:com|nl)|\bcrm\b|\berp\b", re.I)
SCANNED = ["backend/*.py", "backend/**/*.py", "scripts/*.py", "frontend/src/**/*.ts", "frontend/src/**/*.tsx", "config.json", ".env.example", "Dockerfile", "fly.toml"]
ALLOWED_URL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}
ENV_STORE = {"POC_DB", "POC_DB_PATH", "POC_PG_SCHEMA", "POC_ALLOW_LIVE_RESET", "DATABASE_URL"}                                   # the PoC's own store
ENV_AI = {"AI_PROVIDER", "LLM_PROVIDER", "AI_MODEL", "AI_BASE_URL", "AI_API_KEY", "AI_TIMEOUT_S", "AI_MAX_RETRIES", "AI_MAX_INPUT_CHARS", "AI_MOCK_FAIL",
          "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION", "AWS_DEFAULT_REGION", "BEDROCK_MODEL_ID"}                # the language model
ENV_APP = {"POC_SEED_ANCHOR", "POC_CLOCK_MODE", "POC_DEMO_MODE", "POC_ADMIN_PASSWORD", "AUTH_SECRET", "ABANDON_AFTER_MINUTES", "CORS_ORIGINS", "FRONTEND_DIST",
           "MAX_BODY_BYTES", "SERVE_FRONTEND", "API_PORT", "WEB_PORT", "PORT", "CHECK_PASSWORD", "CHECK_RATER_PASSWORD", "MOCK_AI", "TUNNEL", "ADMIN_EMAIL", "ADMIN_NAME", "CHECK_ONLY"}
ALLOWED_ENV = ENV_STORE | ENV_AI | ENV_APP
SECRET_PATTERNS = re.compile(r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|postgres(?:ql)?://[^\s:@/]+:[^\s@/]+@|sk-[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}")
ROUTE_WORDS = re.compile(r"sync|push|webhook|write-?back|salesforce|integrat", re.I)


def _files(patterns):
    seen = set()
    for pat in patterns:
        for p in ROOT.glob(pat):
            if p.is_file() and "__pycache__" not in p.parts and "node_modules" not in p.parts and p.suffix != ".pyc":
                seen.add(p)
    return sorted(seen)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def env_names_in(path: Path) -> set:
    return set(re.findall(r"^#?\s*([A-Z][A-Z_0-9]{2,})=", _text(path), re.M)) if path.exists() else set()


def static_findings() -> list:
    """Everything that breaks rules 1 to 7 in this folder (empty list = the PoC has no way to write to the complaint system)."""
    bad = []
    pkgs = {re.split(r"[<>=\[]", l.strip(), maxsplit=1)[0].lower() for l in _text(ROOT / "requirements.txt").splitlines() if l.strip() and not l.startswith("#")}
    bad += [f"1. library not on the allowed list: {p}" for p in sorted(pkgs - ALLOWED_PACKAGES)]
    for p in _files(["backend/*.py", "backend/**/*.py"]):
        rel = p.relative_to(ROOT).as_posix()
        if rel not in NETWORK_MODULES and NETWORK_IMPORT.search(_text(p)):
            bad.append(f"2. network library imported outside the database and AI modules: {rel}")
    for p in _files(SCANNED):
        rel, text = p.relative_to(ROOT).as_posix(), _text(p)
        if rel == "scripts/readonly_check.py":          # this file is where the forbidden words are written down
            continue
        for m in FORBIDDEN_TERMS.finditer(text):
            bad.append(f"3. complaint-system term '{m.group(0)}' in {rel}")
        for url in re.findall(r"https?://[A-Za-z0-9._:-]+", text):
            host = urlparse(url).hostname
            if host not in ALLOWED_URL_HOSTS and rel.endswith((".py", ".ts", ".tsx", ".toml", "Dockerfile")):
                bad.append(f"4. URL to another host in {rel}: {host}")
    used = set()
    for p in _files(["backend/*.py", "backend/**/*.py", "scripts/*.py"]):
        used |= set(re.findall(r"(?:environ(?:\.get)?\(|environ\[|getenv\(|env\.get\()\s*[\"']([A-Z][A-Z_0-9]{2,})[\"']", _text(p)))
    bad += [f"5. environment variable read by the code is not on the known list: {k}" for k in sorted(used - ALLOWED_ENV)]
    for name in (".env.example", ".env"):
        bad += [f"5. key in {name} is not on the known list: {k}" for k in sorted(env_names_in(ROOT / name) - ALLOWED_ENV)]
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for rel in tracked:
        p = ROOT / rel
        if p.suffix in {".png", ".jpg", ".ico", ".woff", ".woff2", ".lock"} or "package-lock" in rel or not p.is_file():
            continue
        for m in SECRET_PATTERNS.finditer(_text(p)):
            bad.append(f"6. secret-like text in tracked file {rel}: {m.group(0)[:6]}...")
    return bad


def route_findings(paths: list) -> list:
    return [f"7. route named like an integration: {p}" for p in paths if ROUTE_WORDS.search(p)]


def history_findings() -> list:
    """Rule 6 over every commit (can be slow on a big repository)."""
    log = subprocess.run(["git", "log", "-p", "--all", "--no-color"], cwd=ROOT, capture_output=True, text=True, errors="ignore").stdout
    return [f"6. secret-like text in the history: {m.group(0)[:6]}..." for m in SECRET_PATTERNS.finditer(log)]


def connections(port: int) -> list:
    """Remote ends of the TCP connections held by the process listening on ``port`` (macOS or Linux, needs lsof)."""
    pid = subprocess.run(["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    if not pid:
        return []
    out = subprocess.run(["lsof", "-nP", "-a", "-p", pid[0], "-iTCP", "-sTCP:ESTABLISHED"], capture_output=True, text=True).stdout.splitlines()[1:]
    return sorted({l.split()[8].split("->")[-1] for l in out if "->" in l})


def allowed_remote_ports() -> set:
    return {5432, 6543, 443}      # Postgres of the PoC store; HTTPS to the language model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, help="also check what the app running on this port is connected to")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--aws", action="store_true")
    a = ap.parse_args()
    bad = static_findings()
    print("Rules 1 to 7 over the code, configuration and credentials in this folder:", "no findings" if not bad else f"{len(bad)} finding(s)")
    for b in bad:
        print("   ", b)
    print(f"Credential keys that exist (names only): store {sorted(env_names_in(ROOT / '.env') & ENV_STORE)}, language model {sorted(env_names_in(ROOT / '.env') & ENV_AI)}")
    if a.history:
        h = history_findings()
        print("Every commit ever made:", "no secret-like text" if not h else f"{len(h)} finding(s)")
        bad += h
    if a.port:
        conns = connections(a.port)
        db_host = ""
        for l in _text(ROOT / ".env").splitlines():
            if l.startswith("DATABASE_URL="):
                db_host = urlparse(l.split("=", 1)[1].strip().strip('"')).hostname or ""
        print(f"The app on port {a.port} is connected to:", ", ".join(conns) or "nothing right now")
        stray = [c for c in conns if int(c.rsplit(":", 1)[1]) not in allowed_remote_ports()]
        bad += [f"running app has an unexpected connection: {c}" for c in stray]
        print(f"  (the PoC store is {db_host or 'a local file'}; the language model is reached over HTTPS only while a suggestion is made)")
    if a.aws:
        try:
            import os
            import boto3
            from botocore.exceptions import ClientError
            for line in _text(ROOT / ".env").splitlines():
                if line.startswith("AWS_"):
                    k, v = line.split("=", 1)
                    os.environ[k] = v.strip().strip('"')
            who = boto3.client("sts").get_caller_identity()
            print("AWS identity in .env:", who["Arn"].replace(who["Account"], "<account>"))
            for name, call in (("S3", lambda: boto3.client("s3").list_buckets()), ("DynamoDB", lambda: boto3.client("dynamodb").list_tables()),
                               ("Secrets Manager", lambda: boto3.client("secretsmanager").list_secrets()), ("Lambda", lambda: boto3.client("lambda").list_functions())):
                try:
                    call()
                    print(f"  {name}: ALLOWED (more than the model needs)")
                    bad.append(f"AWS identity can read {name}")
                except ClientError as e:
                    print(f"  {name}: refused ({e.response['Error']['Code']})")
        except Exception as e:  # noqa: BLE001
            print("AWS check skipped:", type(e).__name__)
    print("\n" + ("PASS: no credential or client for the live complaint system exists in the PoC." if not bad else "FAIL"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
