"""FastAPI application factory for the Renewi Complaint Registration Assistant PoC.

Synthetic data only; saves go to the local PoC SQLite database. Run with::

    uvicorn backend.app:app --port 8000
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db, seed, settings
from .errors import ApiError
from .routers import accounts, complaints, customers, health_config, review, sessions, testing

log = logging.getLogger("poc")

TAGS = [{"name": "health"}, {"name": "config"}, {"name": "customers"}, {"name": "complaints"},
        {"name": "sessions"}, {"name": "analytics"}, {"name": "review"}]


def _envelope(request: Request, status: int, code: str, message: str, details=None) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    body = {"error": {"code": code, "message": message, "request_id": rid}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status, headers={"X-Request-ID": rid})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the schema and seed synthetic data if the database is empty."""
    db.initialize()
    seed.seed_if_empty()
    yield


# PUBLIC_INTERFACE
def create_app() -> FastAPI:
    """Build the FastAPI app with routers, request IDs, size limits and error envelope."""
    app = FastAPI(title="Renewi Complaint Registration Assistant PoC API",
                  description="Demonstrator backend. SYNTHETIC DATA ONLY. AI is MOCK unless AI_PROVIDER=live. "
                              "Demo-role auth via X-Demo-User header is not production authentication.",
                  version="0.2.0", openapi_tags=TAGS, lifespan=lifespan)
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_body_bytes():
            return _envelope(request, 413, "payload_too_large", "Request body too large.")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def _api(request, exc: ApiError):
        return _envelope(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _val(request, exc: RequestValidationError):
        fields = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return _envelope(request, 422, "validation_error", "Request validation failed.", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, exc: StarletteHTTPException):
        return _envelope(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _any(request, exc: Exception):
        log.exception("Unhandled error")  # stack trace stays in server logs only
        return _envelope(request, 500, "internal_error", "Unexpected error.")

    for r in (health_config.router, accounts.router, customers.router, complaints.router, sessions.router, review.router, testing.router):
        app.include_router(r)
    return app


app = create_app()
