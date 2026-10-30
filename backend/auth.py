"""Request authentication: a signed bearer token from the sign-in page, or (demo mode only) a seeded demo user.

A valid ``Authorization: Bearer`` token identifies a real account (the role is read from the database).
The ``X-Demo-User`` header is NOT production authentication; it is honoured only while demo mode is on
(``POC_DEMO_MODE``, default on for the PoC). Permissions come from ``config.json`` roles and are enforced
here, on the backend.
"""
import time

from fastapi import Depends, Header, Request

from .dbutil import connection
from .errors import ApiError
from .services import accounts
from .settings import get_config


# A temporary password must be replaced before anything else is possible.
_ALLOWED_BEFORE_CHANGE = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout", "/api/auth/options"}


# PUBLIC_INTERFACE
def current_user(request: Request, authorization: str | None = Header(default=None),
                 x_demo_user: str | None = Header(default=None)) -> dict:
    """Resolve the caller: bearer token first, then the demo header when demo mode is on (401 otherwise)."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        hit = accounts._USERS.get(token)                 # checked a moment ago: skip the three database round trips
        if hit and time.monotonic() - hit[0] < accounts._USERS_TTL_S:
            row = hit[1]
        else:
            with connection() as conn:
                uid = accounts.verify_token(conn, token)
                row = accounts.by_id(conn, uid)
                if row:
                    row = dict(row)
            if row and row["status"] == "active":
                if len(accounts._USERS) > 500:
                    accounts._USERS.clear()
                accounts._USERS[token] = (time.monotonic(), row)
        if not row or row["status"] != "active":
            raise ApiError(401, "account_inactive", "This account is not active. Please sign in again.")
        if row["must_change_password"] and request.url.path not in _ALLOWED_BEFORE_CHANGE:
            raise ApiError(403, "password_change_required", "Choose a new password before you continue.")
        return dict(row)
    with connection() as conn:
        if x_demo_user and accounts.demo_mode():
            row = conn.execute("SELECT id,name,role,user_group,function,status,must_change_password FROM users WHERE id=?",
                               (x_demo_user,)).fetchone()
            if not row:
                raise ApiError(401, "unknown_user", "Unknown demo user.")
            return dict(row)
    raise ApiError(401, "auth_required", "Please sign in.")


# PUBLIC_INTERFACE
def require(permission: str):
    """Return a FastAPI dependency enforcing that the user's role grants ``permission``."""

    def dependency(user: dict = Depends(current_user)) -> dict:
        if permission not in get_config()["roles"].get(user["role"], []):
            raise ApiError(403, "forbidden",
                           f"Role '{user['role']}' lacks the '{permission}' permission.")
        return user

    return dependency
