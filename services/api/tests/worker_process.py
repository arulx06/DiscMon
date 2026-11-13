"""Fixture-backed worker entry point for real-signal shutdown tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.db.models.job import Job
from app.db.session import async_session_factory, dispose_engine


async def main() -> None:
    mode, directory = sys.argv[1:]
    markers = Path(directory)
    claim = worker.claim_job
    commit = AsyncSession.commit
    claims = 0

    async def pause(session, phase):
        await session.execute(text("SET application_name = 'discmon-task17d-worker'"))
        markers.joinpath(phase).touch()
        await session.execute(text("SELECT pg_sleep(1.2)"))

    async def claim_job(session, worker_id):
        nonlocal claims
        claims += 1
        markers.joinpath("claims").write_text(str(claims))
        if mode == "claim":
            await pause(session, "waiting")
        job = await claim(session, worker_id)
        if job is None:
            markers.joinpath("idle").touch()
        elif mode == "commit":
            session.info["pause_claim_commit"] = True
        return job

    async def claim_commit(session):
        if session.info.pop("pause_claim_commit", False):
            await pause(session, "waiting")
        await commit(session)

    async def process_job(job):
        markers.joinpath("processing").touch()
        async with async_session_factory() as session:
            current = await session.get(Job, job.id)
            assert current is not None
            current.payload_json = {**current.payload_json, "fixture_effect": "committed"}
            await session.flush()
            if mode in {"success", "failure"}:
                await pause(session, "waiting")
            if mode == "failure":
                raise RuntimeError("fixture-backed worker failure")
            await session.commit()
        markers.joinpath("completed").touch()

    async def watchdog():
        # Baseline exits by its real loop flag, never a forced signal/cancellation.
        await asyncio.sleep(3)
        worker._running = False
        markers.joinpath("watchdog").touch()

    worker.claim_job = claim_job
    worker.process_job = process_job
    AsyncSession.commit = claim_commit
    guard = asyncio.create_task(watchdog())
    try:
        await worker.run_forever()
    finally:
        guard.cancel()
        await asyncio.gather(guard, return_exceptions=True)
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
