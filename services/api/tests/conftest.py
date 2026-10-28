from __future__ import annotations

import asyncio
import os
import selectors
import sys

import pytest_asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://discmon:discmon@127.0.0.1:55432/discmon_test",
)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("OWNER_AUTH_MODE", "disabled")

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
        await connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with async_session_factory() as db_session:
        yield db_session
        await db_session.rollback()
