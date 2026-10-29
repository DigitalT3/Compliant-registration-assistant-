"""Sign-up, sign-in and user administration endpoints."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..auth import current_user, require
from ..dbutil import audit, connection
from ..services import accounts

router = APIRouter(tags=["accounts"])


class RegisterIn(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    function: str = Field(max_length=40)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class UserUpdateIn(BaseModel):
    role: str | None = Field(default=None, max_length=30)
    user_group: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)


@router.get("/api/auth/options", summary="Public sign-up options")
def options():
    """Function categories, password rules and whether demo accounts are enabled (no secrets)."""
    cfg = accounts.settings()
    return {"functions": cfg["functions"], "min_password_length": cfg["min_password_length"],
            "require_approval": cfg["require_approval"], "demo_mode": accounts.demo_mode()}


@router.post("/api/auth/register", status_code=201, summary="Register an employee account")
def register(body: RegisterIn):
    """Create an employee account (role employee). It must be approved by an administrator when approval is on."""
    with connection() as conn:
        return accounts.register(conn, body.name, body.email, body.password, body.function)


@router.post("/api/auth/login", summary="Sign in with e-mail and password")
def login(body: LoginIn):
    """Return a signed, expiring token and the user's profile and permissions."""
    with connection() as conn:
        return accounts.login(conn, body.email, body.password)


@router.get("/api/auth/me", summary="The signed-in user")
def me(user: dict = Depends(current_user)):
    return {**user, "permissions": accounts.permissions(user["role"])}


@router.post("/api/auth/logout", summary="Sign out (recorded in the audit trail)")
def logout(user: dict = Depends(current_user)):
    with connection() as conn:
        audit(conn, user["id"], "logout", {})
        conn.commit()
    return {"ok": True}


@router.get("/api/users", summary="List accounts (administrators)")
def users(status: str | None = Query(default=None, pattern="^(pending|active|disabled)$"),
          user: dict = Depends(require("users"))):
    with connection() as conn:
        return {"items": accounts.list_users(conn, status)}


@router.patch("/api/users/{user_id}", summary="Approve, disable or change role/group (administrators)")
def update_user(user_id: str, body: UserUpdateIn, user: dict = Depends(require("users"))):
    with connection() as conn:
        return accounts.update_user(conn, user, user_id, body.role, body.user_group, body.status)
