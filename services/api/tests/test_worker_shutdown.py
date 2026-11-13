from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app import worker
from app.db.models.enums import JobKind, JobState
from app.db.models.job import Job
from app.db.models.opportunity import Opportunity
from app.db.session import async_session_factory
from app.services.queue import claim_job, recover_expired_jobs
from app.services.time import now_utc

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX process signals"),
]


def row_values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGINT"])
@pytest.mark.parametrize("mode", ["idle", "success", "failure", "claim", "commit"])
async def test_signal_preserves_worker_outcome(session, tmp_path, mode, signal_name):
    now = now_utc()
    pending = Job(
        kind=JobKind.deliver_alert, idempotency_key="pending-preserved",
        available_at=now + timedelta(days=1), payload_json={"provenance": "pending"},
    )
    opportunity = Opportunity(
        title="Preserve opportunity", official_url="https://example.com/preserved",
        first_seen_at=now, last_seen_at=now,
    )
    session.add_all([pending, opportunity])
    if mode != "idle":
        active = Job(
            kind=JobKind.deliver_alert, idempotency_key="active-fixture",
            available_at=now - timedelta(seconds=2), payload_json={"provenance": "active"},
        )
        following = Job(
            kind=JobKind.deliver_alert, idempotency_key="next-must-not-be-claimed",
            available_at=now - timedelta(seconds=1),
        )
        session.add_all([active, following])
    await session.commit()
    preserved = [(row, row_values(row)) for row in [pending, opportunity]]
    if mode != "idle":
        preserved.append((following, row_values(following)))
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests.worker_process", mode, str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        marker = tmp_path / ("idle" if mode == "idle" else "waiting")
        async with asyncio.timeout(10):
            while not await asyncio.to_thread(marker.exists):
                assert process.returncode is None
                await asyncio.sleep(0.005)
        if mode != "idle":
            async with asyncio.timeout(5):
                while not await session.scalar(  # noqa: ASYNC110 - observe child DB state
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE application_name = 'discmon-task17d-worker' "
                        "AND wait_event = 'PgSleep'"
                    )
                ):
                    await session.commit()
                    await asyncio.sleep(0.005)
        claims_at_signal = int((tmp_path / "claims").read_text())
        started = time.monotonic()
        process.send_signal(getattr(signal, signal_name))
        if mode != "idle":
            await asyncio.sleep(0.1)
            assert process.returncode is None, "Must finish the in-flight transaction/job"
    finally:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=12)
    elapsed = time.monotonic() - started
    print(f"mode={mode} {signal_name}-to-exit={elapsed:.3f}s exit={process.returncode}")
    assert process.returncode == 0, stderr.decode()
    assert not (tmp_path / "watchdog").exists(), "Signal did not stop worker"
    assert elapsed < (1 if mode == "idle" else 2.5)
    assert int((tmp_path / "claims").read_text()) == claims_at_signal == 1
    events = [json.loads(line) for line in stdout.splitlines()]
    assert events[0]["event"] == "worker_started"
    assert events[-1]["event"] == "worker_stopped"
    for row, before in preserved:
        await session.refresh(row)
        assert row_values(row) == before
    if mode == "idle":
        assert not (tmp_path / "processing").exists()
        return
    await session.refresh(active)
    assert active.attempts == 1
    assert active.locked_by is None and active.lock_expires_at is None
    assert active.idempotency_key == "active-fixture"
    if mode == "failure":
        assert active.state == JobState.retry_wait
        assert active.available_at > now
        assert active.last_error_redacted == "RuntimeError: fixture-backed worker failure"
        assert active.payload_json == {"provenance": "active"}
        assert not (tmp_path / "completed").exists()
        assert [event["event"] for event in events] == [
            "worker_started", "job_failed", "worker_stopped",
        ]
    else:
        assert active.state == JobState.succeeded
        assert active.last_error_redacted is None
        assert active.payload_json == {"provenance": "active", "fixture_effect": "committed"}
        assert (tmp_path / "completed").exists()
    assert len(list((await session.scalars(select(Job))).all())) == 3
    # Normal recovery leaves a finished/retry job alone, never resurrecting it.
    assert await recover_expired_jobs(session) == 0
    if mode == "failure":
        # Exclude unrelated queued work and prove the failed job is not yet due.
        following.available_at = now + timedelta(days=1)
        assert await claim_job(session, "retry-observer") is None
        active.available_at = now - timedelta(seconds=1)
        await session.flush()
        retry = await claim_job(session, "retry-observer")
        assert retry is not None and retry.id == active.id and retry.attempts == 2
    await session.rollback()


async def test_signal_during_session_entry_prevents_fresh_claim(monkeypatch):
    calls = 0

    class StopOnEntry:
        async def __aenter__(self):
            nonlocal calls
            calls += 1
            if calls == 2:
                worker._running = False
            self.session = async_session_factory()
            return await self.session.__aenter__()

        async def __aexit__(self, *args):
            return await self.session.__aexit__(*args)

    async def forbidden_claim(*args):
        pytest.fail("No claim may begin after shutdown was observed")

    monkeypatch.setattr(worker, "_running", True)
    monkeypatch.setattr(worker, "async_session_factory", StopOnEntry)
    monkeypatch.setattr(worker, "claim_job", forbidden_claim)
    assert await worker.run_once() == 0


async def test_signal_observation_is_serialized_with_claim_guard(monkeypatch):
    handlers = {}
    wakeup = asyncio.Event()
    monkeypatch.setattr(worker, "_running", True)
    monkeypatch.setattr(
        worker.signal, "signal", lambda number, callback: handlers.update({number: callback})
    )
    worker._install_signal_handlers(wakeup)

    # A raw signal between guard and call is observed at the next loop turn.
    assert worker._running
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert worker._running and not wakeup.is_set()
    await asyncio.sleep(0)
    assert not worker._running and wakeup.is_set()
