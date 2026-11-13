"""Isolated scheduler entry point for real-signal regression tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

from app import scheduler
from app.db.session import dispose_engine


async def main() -> None:
    mode, directory = sys.argv[1:]
    markers = Path(directory)
    schedule_once = scheduler.schedule_once
    recover = scheduler.recover_expired_jobs
    calls = 0

    async def slow_recovery(session):
        await session.execute(text("SET application_name = 'discmon-task17c-scheduler'"))
        markers.joinpath("waiting").touch()
        await session.execute(text("SELECT pg_sleep(1.5)"))
        await recover(session)

    async def iteration():
        nonlocal calls
        calls += 1
        markers.joinpath("calls").write_text(str(calls))
        if mode == "database":
            result = await schedule_once()
        elif mode == "error":
            markers.joinpath("waiting").touch()
            while not markers.joinpath("release").exists():  # noqa: ASYNC110 - parent process marker
                await asyncio.sleep(0.01)
            raise RuntimeError("isolated scheduling failure")
        else:
            result = {"queued_sources": 0, "discovery_jobs": [], "invalid_discovery_cadences": []}
        markers.joinpath("completed").touch()
        return result

    async def watchdog():
        # Let the broken baseline exit naturally, never terminate/cancel a transaction.
        await asyncio.sleep(3)
        scheduler._running = False
        markers.joinpath("watchdog").touch()

    scheduler.TICK_SECONDS = 0.05
    scheduler.schedule_once = iteration
    if mode == "database":
        scheduler.recover_expired_jobs = slow_recovery
    guard = asyncio.create_task(watchdog())
    try:
        await scheduler.run_forever()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
