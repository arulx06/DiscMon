from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import JobKind, JobState
from app.db.models.job import Job
from app.db.models.source import Source
from app.services.time import now_utc

LOCK_SECONDS = 300


async def enqueue_job(
    session: AsyncSession,
    kind: JobKind,
    idempotency_key: str,
    *,
    source_id: uuid.UUID | None = None,
    payload_json: dict[str, Any] | None = None,
    available_at: datetime | None = None,
) -> uuid.UUID:
    statement = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            source_id=source_id,
            payload_json=payload_json or {},
            idempotency_key=idempotency_key,
            state=JobState.queued,
            attempts=0,
            max_attempts=4,
            available_at=available_at or now_utc(),
        )
        .on_conflict_do_nothing(index_elements=[Job.idempotency_key])
        .returning(Job.id)
    )
    inserted = await session.scalar(statement)
    if inserted:
        await session.flush()
        return inserted
    existing = await session.scalar(select(Job.id).where(Job.idempotency_key == idempotency_key))
    if existing is None:
        raise RuntimeError("Job insert conflicted but no existing job could be found")
    return existing


async def enqueue_source_job(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    available_at: datetime | None = None,
) -> uuid.UUID | None:
    # Serialize enqueuers without conflicting with webhook foreign-key checks.
    await session.execute(
        select(Source.id).where(Source.id == source_id).with_for_update(key_share=True)
    )
    active = await session.scalar(
        select(Job.id)
        .where(
            Job.source_id == source_id,
            Job.kind == JobKind.ingest_source,
            Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait]),
        )
        .limit(1)
    )
    if active is not None:
        return None
    return await enqueue_job(
        session,
        JobKind.ingest_source,
        f"ingest:{source_id}:{uuid.uuid4()}",
        source_id=source_id,
        available_at=available_at,
    )


async def enqueue_discovery_job(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    idempotency_key: str,
    available_at: datetime | None = None,
) -> uuid.UUID | None:
    active = await session.scalar(
        select(Job.id)
        .where(
            Job.source_id == source_id,
            Job.kind == JobKind.discover_source,
            Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait]),
        )
        .limit(1)
    )
    if active is not None:
        return None
    return await enqueue_job(
        session,
        JobKind.discover_source,
        idempotency_key,
        source_id=source_id,
        available_at=available_at,
    )


async def claim_job(session: AsyncSession, worker_id: str) -> Job | None:
    now = now_utc()
    job = await session.scalar(
        select(Job)
        .where(
            Job.state.in_([JobState.queued, JobState.retry_wait]),
            Job.available_at <= now,
        )
        .order_by(Job.available_at, Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.state = JobState.running
    job.attempts += 1
    job.locked_by = worker_id[:120]
    job.lock_expires_at = now + timedelta(seconds=LOCK_SECONDS)
    await session.flush()
    return job


async def complete_job(session: AsyncSession, job: Job) -> None:
    job.state = JobState.succeeded
    job.locked_by = None
    job.lock_expires_at = None
    job.last_error_redacted = None
    await session.flush()


async def fail_job(session: AsyncSession, job: Job, message: str) -> None:
    job.locked_by = None
    job.lock_expires_at = None
    job.last_error_redacted = message[:1000]
    if job.attempts >= job.max_attempts:
        job.state = JobState.dead
        return
    delay_seconds = min(1800, 30 * (2 ** max(0, job.attempts - 1)))
    job.state = JobState.retry_wait
    job.available_at = now_utc() + timedelta(seconds=delay_seconds)
    await session.flush()


async def recover_expired_jobs(session: AsyncSession) -> int:
    now = now_utc()
    result = await session.execute(
        update(Job)
        .where(
            Job.state == JobState.running,
            Job.lock_expires_at.is_not(None),
            Job.lock_expires_at < now,
        )
        .values(
            state=JobState.retry_wait,
            locked_by=None,
            lock_expires_at=None,
            available_at=now + timedelta(seconds=30),
            last_error_redacted="Worker lock expired; job returned to queue",
        )
        .returning(Job.id)
    )
    return len(result.scalars().all())


async def queued_depth(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Job.state, Job.kind, Job.id).where(
                Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait])
            )
        )
    ).all()
    counts: dict[str, int] = {}
    for state, kind, _ in rows:
        key = f"{state.value}:{kind.value}"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def queue_is_active(session: AsyncSession) -> bool:
    active = await session.scalar(
        select(Job.id)
        .where(Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait]))
        .limit(1)
    )
    return active is not None


async def next_available_at(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(Job.available_at)
        .where(Job.state.in_([JobState.queued, JobState.retry_wait]))
        .order_by(Job.available_at)
        .limit(1)
    )


async def find_active_source_jobs(session: AsyncSession) -> list[Job]:
    jobs = (
        (
            await session.execute(
                select(Job).where(
                    Job.kind == JobKind.ingest_source,
                    Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait]),
                    or_(Job.available_at <= now_utc(), Job.state == JobState.running),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(jobs)
