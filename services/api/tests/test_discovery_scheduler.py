from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import scheduler
from app.db.models.enums import ApprovalStatus, JobKind, JobState, LegalReviewStatus, SourceKind
from app.db.models.job import Job
from app.services import queue
from tests.factories import make_source

pytestmark = pytest.mark.integration


def freeze(monkeypatch, value: str) -> datetime:
    instant = datetime.fromisoformat(value).astimezone(UTC)
    monkeypatch.setattr(scheduler, "now_utc", lambda: instant)
    monkeypatch.setattr(queue, "now_utc", lambda: instant)
    return instant


async def source_for(session: AsyncSession, discovery: dict):
    source = await make_source(
        session,
        kind=SourceKind.static_html,
        url="https://example.org/programmes",
        config={"discovery": discovery},
    )
    source.next_due_at = datetime(2030, 1, 1, tzinfo=UTC)
    return source


async def discovery_jobs(session: AsyncSession) -> list[Job]:
    return list(
        (await session.scalars(select(Job).where(Job.kind == JobKind.discover_source))).all()
    )


@pytest.mark.parametrize(
    ("instant", "month"),
    [
        ("2026-11-01T03:29:59+00:00", None),
        ("2026-11-01T03:30:00+00:00", "2026-11"),
        ("2026-11-02T00:00:00+00:00", "2026-11"),
        ("2026-11-21T02:00:00+00:00", "2026-11"),
        ("2026-11-30T18:29:59+00:00", "2026-11"),
        ("2026-11-30T18:30:00+00:00", None),
        ("2026-12-01T03:30:00+00:00", "2026-12"),
        ("2026-12-31T18:29:59+00:00", "2026-12"),
        ("2026-12-31T18:30:00+00:00", None),
        ("2027-01-01T03:30:00+00:00", "2027-01"),
    ],
)
async def test_monthly_ist_window(session, monkeypatch, instant, month):
    now = freeze(monkeypatch, instant)
    source = await source_for(session, {"enabled": True, "cadence": "monthly"})
    await session.commit()
    result = await scheduler.schedule_once()
    jobs = await discovery_jobs(session)
    assert len(jobs) == (1 if month else 0)
    assert len(result["discovery_jobs"]) == len(jobs)
    if jobs:
        job = jobs[0]
        assert job.source_id == source.id
        assert job.state == JobState.queued
        assert job.available_at == now
        assert job.idempotency_key == f"discover:monthly:{source.id}:{month}"
    print(
        {
            "ist": now.astimezone(scheduler.IST).isoformat(),
            "keys": [job.idempotency_key for job in jobs],
        }
    )


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize(
    ("instant", "eligible"),
    [
        ("2026-11-02T03:29:59+00:00", False),
        ("2026-11-02T03:30:00+00:00", True),
        ("2026-11-02T18:29:59+00:00", True),
        ("2026-11-03T03:30:00+00:00", False),
    ],
)
async def test_weekly_default_unchanged(session, monkeypatch, explicit, instant, eligible):
    freeze(monkeypatch, instant)
    config = {"enabled": True}
    if explicit:
        config["cadence"] = "weekly"
    source = await source_for(session, config)
    await session.commit()
    await scheduler.schedule_once()
    await scheduler.schedule_once()
    jobs = await discovery_jobs(session)
    assert len(jobs) == int(eligible)
    if jobs:
        assert jobs[0].idempotency_key == f"discover:weekly:{source.id}:2026-W45"


async def test_monthly_restart_repeated_ticks_and_next_month(session, monkeypatch):
    source = await source_for(session, {"enabled": True, "cadence": "monthly"})
    await session.commit()
    freeze(monkeypatch, "2026-11-01T03:30:00+00:00")
    await scheduler.schedule_once()
    # A completed job must still deduplicate after a restart and UTC date changes.
    job = (await discovery_jobs(session))[0]
    job.state = JobState.succeeded
    await session.commit()
    importlib.reload(scheduler)
    for instant in [
        "2026-11-01T03:31:00+00:00",
        "2026-11-01T23:59:00+00:00",
        "2026-11-02T00:01:00+00:00",
        "2026-11-30T18:29:59+00:00",
    ]:
        freeze(monkeypatch, instant)
        await scheduler.schedule_once()
        assert len(await discovery_jobs(session)) == 1
    freeze(monkeypatch, "2026-12-01T03:30:00+00:00")
    await scheduler.schedule_once()
    keys = {job.idempotency_key for job in await discovery_jobs(session)}
    assert keys == {
        f"discover:monthly:{source.id}:2026-11",
        f"discover:monthly:{source.id}:2026-12",
    }
    print({"restart_and_month_keys": sorted(keys)})


@pytest.mark.parametrize("state", [JobState.queued, JobState.running, JobState.retry_wait])
async def test_active_discovery_blocks_only_its_source(session, monkeypatch, state):
    now = freeze(monkeypatch, "2026-11-02T03:30:00+00:00")
    first = await source_for(session, {"enabled": True, "cadence": "monthly"})
    second = await source_for(session, {"enabled": True, "cadence": "monthly"})
    weekly = await source_for(session, {"enabled": True})
    active_id = await queue.enqueue_discovery_job(
        session, first.id, idempotency_key=f"discover:monthly:{first.id}:2026-10"
    )
    active = await session.get(Job, active_id)
    active.state = state
    active.lock_expires_at = datetime(2030, 1, 1, tzinfo=UTC)
    await session.commit()
    await scheduler.schedule_once()
    jobs = await discovery_jobs(session)
    assert {job.idempotency_key for job in jobs} == {
        f"discover:monthly:{first.id}:2026-10",
        f"discover:monthly:{second.id}:2026-11",
        f"discover:weekly:{weekly.id}:2026-W45",
    }
    # Completion allows current-month catch-up, not historical backfill.
    await session.refresh(active)
    assert active.state == state
    await queue.complete_job(session, active)
    await session.commit()
    await scheduler.schedule_once()
    jobs = await discovery_jobs(session)
    assert len(jobs) == 4
    assert any(job.idempotency_key == f"discover:monthly:{first.id}:2026-11" for job in jobs)
    print(
        {
            "active_state": state.value,
            "ist": now.astimezone(scheduler.IST).isoformat(),
            "keys": [job.idempotency_key for job in jobs],
        }
    )


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("enabled", False),
        ("approval_status", ApprovalStatus.candidate),
        ("approval_status", ApprovalStatus.rejected),
        ("legal_review_status", LegalReviewStatus.pending),
        ("legal_review_status", LegalReviewStatus.rejected),
        ("config_json", {"discovery": {"enabled": False, "cadence": "monthly"}}),
        ("config_json", {}),
    ],
)
async def test_monthly_authorization_gates(session, monkeypatch, attribute, value):
    freeze(monkeypatch, "2026-11-02T03:30:00+00:00")
    source = await source_for(session, {"enabled": True, "cadence": "monthly"})
    setattr(source, attribute, value)
    await session.commit()
    result = await scheduler.schedule_once()
    assert result["discovery_jobs"] == []
    assert await discovery_jobs(session) == []


@pytest.mark.parametrize("invalid", ["daily", "Monthly", "", None, False, 7, [], {}, ["monthly"]])
async def test_invalid_cadence_fails_closed_without_blocking_other_work(
    session, monkeypatch, invalid
):
    freeze(monkeypatch, "2026-11-02T03:30:00+00:00")
    invalid_source = await source_for(session, {"enabled": True, "cadence": invalid})
    invalid_source.next_due_at = None
    monthly = await source_for(session, {"enabled": True, "cadence": "monthly"})
    weekly = await source_for(session, {"enabled": True})
    await session.commit()
    result = await scheduler.schedule_once()
    jobs = await discovery_jobs(session)
    assert {job.source_id for job in jobs} == {monthly.id, weekly.id}
    assert result["invalid_discovery_cadences"] == 1
    assert result["alert_job"] is not None
    assert len(result["digest_jobs"]) == 1
    assert result["queued_sources"] == 1
    assert (
        await session.scalar(
            select(Job).where(Job.kind == JobKind.ingest_source, Job.source_id == invalid_source.id)
        )
        is not None
    )
