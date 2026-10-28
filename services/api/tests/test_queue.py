from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import JobKind, JobState
from app.db.session import async_session_factory
from app.services.queue import claim_job, enqueue_job


async def test_two_workers_cannot_claim_the_same_job(session: AsyncSession) -> None:
    job_id = await enqueue_job(session, JobKind.ingest_source, "claim-contention-test")
    await session.commit()

    first = await claim_job(session, "worker-a")
    assert first is not None
    assert first.id == job_id
    assert first.state == JobState.running

    async with async_session_factory() as second_session:
        second = await claim_job(second_session, "worker-b")
        assert second is None
        await second_session.rollback()

    await session.rollback()
