"""Demo-role authentication. NOT production auth: the caller names a seeded demo user.

The ``X-Demo-User`` header selects a seeded user; permissions come from
``config.json`` roles and are enforced here, on the backend.
"""
from fastapi import Depends, Header

from .dbutil import connection
from .errors import ApiError
from .settings import get_config


# PUBLIC_INTERFACE
def current_user(x_demo_user: str | None = Header(default=None)) -> dict:
    """Resolve the seeded demo user from the ``X-Demo-User`` header (401 if absent/unknown)."""
    if not x_demo_user:
        raise ApiError(401, "auth_required", "Select a demo user (X-Demo-User header).")
    with connection() as conn:
        row = conn.execute("SELECT id,name,role,user_group FROM users WHERE id=?",
                           (x_demo_user,)).fetchone()
    if not row:
        raise ApiError(401, "unknown_user", "Unknown demo user.")
    return dict(row)


# PUBLIC_INTERFACE
def require(permission: str):
    """Return a FastAPI dependency enforcing that the user's role grants ``permission``."""

    def dependency(user: dict = Depends(current_user)) -> dict:
        if permission not in get_config()["roles"].get(user["role"], []):
            raise ApiError(403, "forbidden",
                           f"Role '{user['role']}' lacks the '{permission}' permission.")
        return user

    return dependency
