from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app import scheduler
from app.db.models.enums import JobKind, JobState
from app.db.models.job import Job
from app.db.models.opportunity import Opportunity
from app.services.time import now_utc
from tests.factories import make_source

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process signals")


async def wait_for_marker(process, marker: Path) -> None:
    async with asyncio.timeout(10):
        while not await asyncio.to_thread(marker.exists):
            assert process.returncode is None
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("mode", ["idle", "database", "error"])
async def test_sigterm_finishes_only_current_iteration(session, tmp_path, mode):
    source = await make_source(session)
    pending = Job(kind=JobKind.deliver_alert, idempotency_key="preserved-pending-job")
    opportunity = Opportunity(
        title="Preserve me", official_url="https://example.com/preserved",
        first_seen_at=now_utc(), last_seen_at=now_utc(),
    )
    session.add_all([pending, opportunity])
    await session.commit()
    before_opportunity = {
        column.name: getattr(opportunity, column.name) for column in Opportunity.__table__.columns
    }
    before_pending = {
        column.name: getattr(pending, column.name) for column in Job.__table__.columns
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.scheduler_process",
        mode,
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(os.environ),
    )
    marker = "completed" if mode == "idle" else "waiting"
    await wait_for_marker(process, tmp_path / marker)
    if mode == "database":
        async with asyncio.timeout(5):
            while not await session.scalar(  # noqa: ASYNC110 - observe an external DB wait
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE application_name = 'discmon-task17c-scheduler' "
                    "AND wait_event = 'PgSleep'"
                )
            ):
                await session.commit()
                await asyncio.sleep(0.005)
    calls_at_signal = int((tmp_path / "calls").read_text())
    started = time.monotonic()
    process.send_signal(signal.SIGTERM)
    if mode != "idle":
        await asyncio.sleep(0.1)
        assert process.returncode is None, "In-flight iteration must not be cancelled"
    (tmp_path / "release").touch()
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    elapsed = time.monotonic() - started
    print(f"mode={mode} SIGTERM-to-exit={elapsed:.3f}s exit={process.returncode}")
    assert process.returncode == 0, stderr.decode()
    assert not (tmp_path / "watchdog").exists(), "SIGTERM did not stop scheduler"
    assert elapsed < (2.5 if mode == "database" else 1)
    assert int((tmp_path / "calls").read_text()) == calls_at_signal
    events = [json.loads(line) for line in stdout.splitlines()]
    assert events[0]["event"] == "scheduler_started"
    assert events[-1]["event"] == "scheduler_stopped"
    if mode == "error":
        assert any(event["event"] == "scheduler_error" for event in events)
    else:
        assert (tmp_path / "completed").exists()
    await session.refresh(opportunity)
    await session.refresh(pending)
    assert before_opportunity == {
        column.name: getattr(opportunity, column.name) for column in Opportunity.__table__.columns
    }
    assert before_pending == {
        column.name: getattr(pending, column.name) for column in Job.__table__.columns
    }
    source_jobs = list((await session.scalars(select(Job).where(Job.source_id == source.id))).all())
    if mode == "database":
        assert len(source_jobs) == 1
        assert source_jobs[0].state == JobState.queued
        assert source_jobs[0].attempts == 0
    else:
        assert not source_jobs


async def test_idle_wait_is_woken_without_waiting_for_tick(monkeypatch):
    installed = asyncio.Event()
    stop = None

    def install(event):
        nonlocal stop
        stop = event

    async def iteration():
        installed.set()
        return {"queued_sources": 0, "discovery_jobs": [], "invalid_discovery_cadences": []}

    monkeypatch.setattr(scheduler, "_install_signal_handlers", install)
    monkeypatch.setattr(scheduler, "_running", True)
    monkeypatch.setattr(scheduler, "schedule_once", iteration)
    monkeypatch.setattr(scheduler, "TICK_SECONDS", 3600)
    task = asyncio.create_task(scheduler.run_forever())
    await installed.wait()
    assert stop is not None
    scheduler._running = False
    stop.set()
    await asyncio.wait_for(task, timeout=1)
