from __future__ import annotations

import argparse
import asyncio
import json
import signal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.db.models.enums import (
    ApprovalStatus,
    HealthStatus,
    JobKind,
    LegalReviewStatus,
)
from app.db.models.source import Source
from app.db.session import async_session_factory
from app.runtime import run
from app.services.queue import enqueue_job, enqueue_source_job, recover_expired_jobs
from app.services.time import now_utc

_running = True
TICK_SECONDS = 30
IST = ZoneInfo("Asia/Kolkata")


def _install_signal_handlers() -> None:
    global _running

    def stop(*_: object) -> None:
        _running = False

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), stop)
            except (ValueError, OSError):
                pass


async def schedule_once() -> dict:
    now = now_utc()
    queued_sources = 0
    async with async_session_factory() as session:
        await recover_expired_jobs(session)
        sources = (
            (
                await session.execute(
                    select(Source)
                    .where(
                        Source.enabled.is_(True),
                        Source.approval_status == ApprovalStatus.approved,
                        Source.legal_review_status == LegalReviewStatus.approved,
                        Source.health_status != HealthStatus.failing,
                        or_(Source.next_due_at.is_(None), Source.next_due_at <= now),
                    )
                    .order_by(Source.next_due_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for source in sources:
            job_id = await enqueue_source_job(session, source.id, available_at=now)
            if job_id is not None:
                queued_sources += 1
        alert_job = await enqueue_job(
            session,
            JobKind.deliver_alert,
            f"deliver-alerts:{now.strftime('%Y%m%d%H%M')}",
            available_at=now,
        )
        local = now.astimezone(IST)
        digest_jobs: list[str] = []
        if (local.hour, local.minute) >= (8, 30):
            daily_job = await enqueue_job(
                session,
                JobKind.generate_digest,
                f"digest:daily:{local.strftime('%Y%m%d')}",
                payload_json={"kind": "daily"},
                available_at=now,
            )
            digest_jobs.append(str(daily_job))
        if local.weekday() == 6 and local.hour >= 19:
            weekly_job = await enqueue_job(
                session,
                JobKind.generate_digest,
                f"digest:weekly:{local.strftime('%G-W%V')}",
                payload_json={"kind": "weekly"},
                available_at=now,
            )
            digest_jobs.append(str(weekly_job))
        await session.commit()
    return {
        "queued_sources": queued_sources,
        "alert_job": str(alert_job) if alert_job else None,
        "digest_jobs": digest_jobs,
    }


async def run_forever() -> None:
    _install_signal_handlers()
    print(json.dumps({"event": "scheduler_started"}), flush=True)
    while _running:
        try:
            result = await schedule_once()
            if result["queued_sources"]:
                print(json.dumps({"event": "scheduler_tick", **result}), flush=True)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "scheduler_error",
                        "error": type(exc).__name__,
                        "message": str(exc)[:300],
                    }
                ),
                flush=True,
            )
        await asyncio.sleep(TICK_SECONDS)
    print(json.dumps({"event": "scheduler_stopped"}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="DiscMon scheduler")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run(schedule_once())), flush=True)
    else:
        run(run_forever())


if __name__ == "__main__":
    main()
