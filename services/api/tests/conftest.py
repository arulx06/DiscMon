from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import selectors
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from psycopg import ConnectionInfo, NotSupportedError

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, repr=False)
class TestDatabaseTarget:
    database: str
    username: str
    password: str | None
    host: str
    port: int


def _database_target(value: str) -> TestDatabaseTarget:
    try:
        url = make_url(value)
        port = url.port if url.port is not None else 5432
    except Exception:
        raise pytest.UsageError("Test database safety: malformed database URL") from None
    if url.drivername != "postgresql+psycopg":
        raise pytest.UsageError("Test database safety: use postgresql+psycopg")
    if not url.database or not re.fullmatch(r"[a-z][a-z0-9_]*_test", url.database):
        raise pytest.UsageError("Test database safety: database name must end in _test")
    if not url.username or not 1 <= port <= 65535:
        raise pytest.UsageError("Test database safety: explicit user and valid port required")

    # Reject libpq routing/options, including duplicate and multi-host parameters.
    if set(url.query) - {"host"}:
        raise pytest.UsageError("Test database safety: unexpected URL query parameters")
    socket = url.query.get("host")
    if socket is not None:
        if (
            url.host
            or not isinstance(socket, str)
            or not (
                socket == "/var/run/postgresql"
                or re.fullmatch(r"/tmp/discmon-test-[a-zA-Z0-9_-]+", socket)
            )
        ):
            raise pytest.UsageError("Test database safety: unapproved Unix socket or host override")
        host = socket
    else:
        host = url.host or ""
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise pytest.UsageError("Test database safety: explicit loopback host required")
    return TestDatabaseTarget(url.database, url.username, url.password, host, port)


def validate_test_environment(environ: Mapping[str, str]) -> TestDatabaseTarget:
    if environ.get("APP_ENV") != "test":
        raise pytest.UsageError("Test database safety: explicitly set APP_ENV=test")
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        if not environ.get(key):
            raise pytest.UsageError(f"Test database safety: explicitly set {key}")
    if any(key.upper().startswith("PG") for key in environ):
        raise pytest.UsageError("Test database safety: remove inherited PG* connection settings")
    if any(
        key.upper() in {"APP_ENV", "DATABASE_URL", "TEST_DATABASE_URL"} and key != key.upper()
        for key in environ
    ):
        raise pytest.UsageError("Test database safety: ambiguous environment variable casing")
    target = _database_target(environ["DATABASE_URL"])
    if target != _database_target(environ["TEST_DATABASE_URL"]):
        raise pytest.UsageError("Test database safety: DATABASE_URL and TEST_DATABASE_URL differ")
    return target


def validate_connected_database(
    target: TestDatabaseTarget,
    engine_url: URL,
    identity: Mapping[str, Any],
    connection_info: ConnectionInfo,
) -> None:
    if _database_target(engine_url.render_as_string(hide_password=False)) != target:
        raise pytest.UsageError("Test database safety: engine target changed")
    if (
        identity["database"] != target.database
        or identity["username"] != target.username
        or identity["session_username"] != target.username
    ):
        raise pytest.UsageError("Test database safety: connected database/user identity mismatch")
    # Use the client endpoint: CI's Docker port mapping changes the server-side address/port.
    if (
        connection_info.host != target.host
        or connection_info.port != target.port
        or connection_info.dbname != target.database
        or connection_info.user != target.username
    ):
        raise pytest.UsageError("Test database safety: connected server endpoint mismatch")
    try:
        address = connection_info.hostaddr
    except (AttributeError, NotSupportedError):
        raise pytest.UsageError("Test database safety: resolved endpoint unavailable") from None
    if target.host.startswith("/"):
        matches = address in (None, "")
    else:
        allowed = {"127.0.0.1", "::1"} if target.host == "localhost" else {target.host}
        try:
            matches = str(ipaddress.ip_address(address)) in allowed
        except ValueError:
            matches = False
    if not matches:
        raise pytest.UsageError("Test database safety: resolved endpoint is not approved loopback")


# This must run before importing app.db.session (which constructs the engine).
_test_database_target = validate_test_environment(os.environ)
os.environ.setdefault("OWNER_AUTH_MODE", "disabled")

from app.config import get_settings  # noqa: E402

if (
    get_settings().app_env != "test"
    or _database_target(get_settings().database_url) != _test_database_target
):
    raise pytest.UsageError("Test database safety: effective application settings differ")

from app.db.base import Base  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def pytest_asyncio_loop_factories(config, item):
    return {"selector": _selector_loop}


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        identity = (
            (
                await connection.execute(
                    text(
                        "SELECT current_database() AS database, current_user AS username, "
                        "session_user AS session_username"
                    )
                )
            )
            .mappings()
            .one()
        )
        raw_connection = await connection.get_raw_connection()
        validate_connected_database(
            _test_database_target, engine.url, identity, raw_connection.driver_connection.info
        )
        await connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with async_session_factory() as db_session:
        yield db_session
        await db_session.rollback()
