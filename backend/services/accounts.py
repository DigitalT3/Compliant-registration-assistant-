"""Employee accounts: registration, password login, signed session tokens and admin approval.

Passwords are stored as salted scrypt hashes, never in clear text. Tokens are stateless, HMAC-signed
and expire; the role is always read from the database, never from the token. This is the PoC's own
sign-in: replace ``verify_token`` and ``login`` with the client's identity provider (OIDC/SSO) later
without touching the screens or the permission checks.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_PUBLIC = "id,name,email,role,user_group,function,status,must_change_password"


def settings() -> dict:
    return get_config()["auth"]


def demo_mode() -> bool:
    """Demo accounts (X-Demo-User header, no password) are OFF unless POC_DEMO_MODE=1. Never enable them in a shared deployment."""
    return os.environ.get("POC_DEMO_MODE", "0") == "1"


# --- passwords -----------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check; runs a dummy hash when there is no stored hash so timing does not reveal accounts."""
    try:
        _, salt, digest = (stored or "scrypt$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 43 + "=").split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected) and stored is not None


# --- tokens --------------------------------------------------------------------------------------

def _secret(conn) -> bytes:
    env = os.environ.get("AUTH_SECRET")
    if env:
        return env.encode()
    row = conn.execute("SELECT value FROM app_settings WHERE key='auth_secret'").fetchone()
    if not row:  # generated once and kept in the database, so tokens survive restarts without extra setup
        conn.execute("INSERT INTO app_settings(key,value) VALUES('auth_secret',?) ON CONFLICT(key) DO NOTHING",
                     (secrets.token_hex(32),))
        conn.commit()
        row = conn.execute("SELECT value FROM app_settings WHERE key='auth_secret'").fetchone()
    return row[0].encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _fingerprint(password_hash: str | None) -> str:
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:12]


def issue_token(conn, user_id: str, password_hash: str | None = None) -> tuple[str, int]:
    ttl = int(settings()["token_ttl_minutes"]) * 60
    if password_hash is None:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        password_hash = row and row["password_hash"]
    body = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl, "pv": _fingerprint(password_hash)}).encode())
    sig = _b64(hmac.new(_secret(conn), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", ttl


def verify_token(conn, token: str) -> str:
    """Return the user id in a valid, unexpired token or raise 401. A token ends when the password changes."""
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(_secret(conn), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(data["exp"]) < time.time():
            raise ApiError(401, "session_expired", "Your session has expired. Please sign in again.")
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (data["sub"],)).fetchone()
        if not row or data.get("pv") != _fingerprint(row["password_hash"]):
            raise ApiError(401, "session_expired", "Your session has ended. Please sign in again.")
        return data["sub"]
    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - any malformed token is simply invalid
        raise ApiError(401, "invalid_token", "Please sign in again.")


# --- helpers -------------------------------------------------------------------------------------

def permissions(role: str) -> list:
    return get_config()["roles"].get(role, [])


def public(row) -> dict:
    d = {k: row[k] for k in _PUBLIC.split(",")}
    d["permissions"] = permissions(d["role"])
    return d


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def by_id(conn, user_id: str):
    return conn.execute(f"SELECT {_PUBLIC} FROM users WHERE id=?", (user_id,)).fetchone()


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not 2 <= len(name) <= 80:
        raise ApiError(422, "invalid_name", "Enter your full name (2 to 80 characters).")
    return name


def _check_password(password: str, email: str) -> None:
    need = int(settings()["min_password_length"])
    if len(password or "") < need:
        raise ApiError(422, "weak_password", f"Use a password of at least {need} characters.")
    if password.lower() == email.lower():
        raise ApiError(422, "weak_password", "The password cannot be your e-mail address.")


# --- registration and login ----------------------------------------------------------------------

def register(conn, name: str, email: str, password: str, function: str) -> dict:
    cfg = settings()
    email = (email or "").strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise ApiError(422, "invalid_email", "Enter a valid e-mail address.")
    domains = [d.lower() for d in cfg.get("allowed_email_domains", [])]
    if domains and email.rsplit("@", 1)[1] not in domains:
        raise ApiError(422, "email_domain_not_allowed", "Use your company e-mail address.")
    if function not in {f["id"] for f in cfg["functions"]}:
        raise ApiError(422, "invalid_function", "Choose your function: customer service, sales or site operations.")
    name = _clean_name(name)
    _check_password(password, email)
    if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
        raise ApiError(409, "email_taken", "An account with this e-mail address already exists.")
    status = "pending" if cfg["require_approval"] else "active"
    uid = _insert(conn, name, email, password, function, "employee", status, must_change=False)
    audit(conn, uid, "account_registered", {"function": function, "status": status})
    conn.commit()
    return {"id": uid, "status": status}


def _insert(conn, name, email, password, function, role, status, must_change) -> str:
    uid = "u_" + secrets.token_hex(5)
    conn.execute("INSERT INTO users(id,name,role,user_group,email,password_hash,function,status,created_at,"
                 "failed_logins,must_change_password) VALUES(?,?,?,?,?,?,?,?,?,0,?)",
                 (uid, name, role, function, email, hash_password(password), function, status, db.now(),
                  int(must_change)))
    return uid


_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters


def temporary_password() -> str:
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(14))


def create_account(conn, actor_id: str | None, name: str, email: str, password: str, function: str, role: str,
                   must_change: bool) -> str:
    """Create an active account directly (administrator action or the first-admin command)."""
    cfg = settings()
    email = (email or "").strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise ApiError(422, "invalid_email", "Enter a valid e-mail address.")
    if function and function not in {f["id"] for f in cfg["functions"]}:
        raise ApiError(422, "invalid_function", "Choose a valid function.")
    if role not in get_config()["roles"]:
        raise ApiError(422, "invalid_role", "Unknown role.")
    if role == "lead" and not function:
        raise ApiError(422, "team_required", "Choose the team this lead leads.")
    name = _clean_name(name)
    _check_password(password, email)
    if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
        raise ApiError(409, "email_taken", "An account with this e-mail address already exists.")
    uid = _insert(conn, name, email, password, function or None, role, "active", must_change)
    audit(conn, actor_id or uid, "account_created", {"user": uid, "role": role, "by_admin": bool(actor_id)})
    conn.commit()
    return uid


def admin_create(conn, actor: dict, name, email, function, role) -> dict:
    temp = temporary_password()
    uid = create_account(conn, actor["id"], name, email, temp, function, role, must_change=True)
    return {"user": public(by_id(conn, uid)), "temporary_password": temp}


def admin_reset_password(conn, actor: dict, user_id: str) -> dict:
    target = conn.execute("SELECT id,email FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        raise ApiError(404, "user_not_found", "User not found.")
    if not target["email"]:
        raise ApiError(422, "no_password_login", "This is a demo account without a password.")
    temp = temporary_password()
    conn.execute("UPDATE users SET password_hash=?, must_change_password=1, failed_logins=0, locked_until=NULL WHERE id=?",
                 (hash_password(temp), user_id))
    audit(conn, actor["id"], "password_reset_by_admin", {"user": user_id})
    conn.commit()
    return {"user": public(by_id(conn, user_id)), "temporary_password": temp}


def change_password(conn, user_id: str, current: str, new: str) -> dict:
    row = conn.execute("SELECT email,password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row["email"]:
        raise ApiError(422, "no_password_login", "This account does not use a password.")
    if not verify_password(current or "", row["password_hash"]):
        raise ApiError(403, "wrong_password", "The current password is not correct.")
    _check_password(new, row["email"])
    if verify_password(new, row["password_hash"]):
        raise ApiError(422, "same_password", "Choose a password you have not used before.")
    new_hash = hash_password(new)
    conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (new_hash, user_id))
    audit(conn, user_id, "password_changed", {})
    conn.commit()
    token, ttl = issue_token(conn, user_id, new_hash)      # older tokens stop working; this is the new session
    return {"token": token, "expires_in": ttl, "user": public(by_id(conn, user_id))}


def login(conn, email: str, password: str) -> dict:
    cfg = settings()
    email = (email or "").strip().lower()
    row = conn.execute(f"SELECT {_PUBLIC},password_hash,failed_logins,locked_until FROM users "
                       "WHERE lower(email)=?", (email,)).fetchone()
    if row and row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > _utc_now():
        raise ApiError(429, "account_locked", "Too many failed attempts. Try again in a few minutes.")
    if not verify_password(password or "", row["password_hash"] if row else None) or not row:
        if row:
            failed = (row["failed_logins"] or 0) + 1
            locked = None
            if failed >= int(cfg["max_failed_logins"]):
                locked = (_utc_now() + timedelta(minutes=int(cfg["lockout_minutes"]))).isoformat()
                failed = 0
            conn.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (failed, locked, row["id"]))
            audit(conn, row["id"], "login_failed", {"locked": bool(locked)})
            conn.commit()
        raise ApiError(401, "invalid_credentials", "Incorrect e-mail address or password.")
    if row["status"] == "pending":
        raise ApiError(403, "account_pending", "Your account is waiting for approval by an administrator.")
    if row["status"] != "active":
        raise ApiError(403, "account_disabled", "This account is disabled. Contact an administrator.")
    conn.execute("UPDATE users SET failed_logins=0, locked_until=NULL, last_login_at=? WHERE id=?", (db.now(), row["id"]))
    audit(conn, row["id"], "login", {})
    conn.commit()
    token, ttl = issue_token(conn, row["id"])
    return {"token": token, "expires_in": ttl, "user": public(row)}


# --- administration ------------------------------------------------------------------------------

def list_users(conn, status: str | None = None) -> list:
    sql = f"SELECT {_PUBLIC},created_at,last_login_at FROM users"
    args = []
    if status:
        sql, args = sql + " WHERE status=?", [status]
    return [{**{k: r[k] for k in (_PUBLIC + ",created_at,last_login_at").split(",")},
             "permissions": permissions(r["role"])}
            for r in conn.execute(sql + " ORDER BY (status='pending') DESC, name", args)]


def _active_admins(conn) -> int:
    return conn.execute("SELECT count(*) FROM users WHERE role='admin' AND status='active'").fetchone()[0]


def update_user(conn, actor: dict, user_id: str, role=None, user_group=None, status=None, function=None) -> dict:
    target = by_id(conn, user_id)
    if not target:
        raise ApiError(404, "user_not_found", "User not found.")
    if role is not None and role not in get_config()["roles"]:
        raise ApiError(422, "invalid_role", "Unknown role.")
    if function is not None and function not in {f["id"] for f in settings()["functions"]}:
        raise ApiError(422, "invalid_function", "Choose a valid function.")
    if (role or target["role"]) == "lead" and not (function or target["function"]):
        raise ApiError(422, "team_required", "Choose the team this lead leads.")
    if status is not None and status not in ("active", "disabled"):
        raise ApiError(422, "invalid_status", "Status must be active or disabled.")
    losing_admin = target["role"] == "admin" and target["status"] == "active" and (
        (role is not None and role != "admin") or status == "disabled")
    if losing_admin and _active_admins(conn) <= 1:
        raise ApiError(409, "last_admin", "There must be at least one active administrator.")
    if user_id == actor["id"] and status == "disabled":
        raise ApiError(409, "self_disable", "You cannot disable your own account.")
    new_function = function or target["function"]
    if function and not user_group:
        user_group = function                  # a person's team is their function; sessions record it from here on
    new = {"role": role or target["role"], "user_group": user_group or target["user_group"],
           "status": status or target["status"], "function": new_function}
    if all(new[k] == target[k] for k in new):
        return public(target)          # nothing changes (e.g. a double click): no write, no audit entry
    conn.execute("UPDATE users SET role=?, user_group=?, status=?, function=? WHERE id=?",
                 (new["role"], new["user_group"], new["status"], new["function"], user_id))
    audit(conn, actor["id"], "user_updated", {"user": user_id, "from": {k: target[k] for k in new}, "to": new})
    conn.commit()
    return public(by_id(conn, user_id))
