from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import get_settings
from app.db.session import dispose_engine, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(
    title="DiscMon API",
    version="0.1.0",
    docs_url="/api/docs" if settings.is_local else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.is_local else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(router)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid.uuid4().hex)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "http_error",
            "message": str(exc.detail),
            "request_id": _request_id(request),
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Request validation failed",
            "request_id": _request_id(request),
            "details": exc.errors(),
        },
    )


@app.exception_handler(HTTPException)
async def fastapi_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "http_error",
            "message": str(exc.detail),
            "request_id": _request_id(request),
        },
        headers=exc.headers,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id[:120]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id[:120]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health/live", include_in_schema=False)
@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"status": "ok", "service": "discmon-api"}


@app.get("/health/ready", include_in_schema=False)
@app.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unreachable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "database": "ok"})
