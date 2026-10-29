"""Request authentication: a signed bearer token from the sign-in page, or (demo mode only) a seeded demo user.

A valid ``Authorization: Bearer`` token identifies a real account (the role is read from the database).
The ``X-Demo-User`` header is NOT production authentication; it is honoured only while demo mode is on
(``POC_DEMO_MODE``, default on for the PoC). Permissions come from ``config.json`` roles and are enforced
here, on the backend.
"""
from fastapi import Depends, Header

from .dbutil import connection
from .errors import ApiError
from .services import accounts
from .settings import get_config


# PUBLIC_INTERFACE
def current_user(authorization: str | None = Header(default=None),
                 x_demo_user: str | None = Header(default=None)) -> dict:
    """Resolve the caller: bearer token first, then the demo header when demo mode is on (401 otherwise)."""
    with connection() as conn:
        if authorization and authorization.lower().startswith("bearer "):
            uid = accounts.verify_token(conn, authorization[7:].strip())
            row = accounts.by_id(conn, uid)
            if not row or row["status"] != "active":
                raise ApiError(401, "account_inactive", "This account is not active. Please sign in again.")
            return dict(row)
        if x_demo_user and accounts.demo_mode():
            row = conn.execute("SELECT id,name,role,user_group,function,status FROM users WHERE id=?",
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
