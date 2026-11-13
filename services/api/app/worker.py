from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import uuid

from sqlalchemy import select

from app.db.models.enums import JobKind
from app.db.models.job import Job
from app.db.session import async_session_factory
from app.runtime import run
from app.services.ingestion import ingest_source
from app.services.queue import claim_job, complete_job, fail_job, recover_expired_jobs

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
_running = True


def _install_signal_handlers(wakeup: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def stop(*_: object) -> None:
        global _running
        _running = False
        loop.call_soon_threadsafe(wakeup.set)

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), stop)
            except (ValueError, OSError):
                pass


async def process_job(job: Job) -> None:
    if job.kind == JobKind.ingest_source:
        if job.source_id is None:
            raise ValueError("ingest_source job has no source_id")
        async with async_session_factory() as session:
            outcome = await ingest_source(session, job.source_id, job_id=job.id)
            await session.commit()
            print(
                json.dumps(
                    {
                        "event": "source_ingest",
                        "source_id": str(job.source_id),
                        "run_id": str(outcome.run_id),
                        "status": outcome.status,
                        "seen": outcome.records_seen,
                        "created": outcome.created,
                        "updated": outcome.updated,
                        "skipped": outcome.skipped,
                        "scan_complete": outcome.scan_complete,
                    }
                ),
                flush=True,
            )
        return
    if job.kind == JobKind.discover_source:
        if job.source_id is None:
            raise ValueError("discover_source job has no source_id")
        from app.services.discovery import run_discovery

        async with async_session_factory() as session:
            discovery_outcome = await run_discovery(session, job.source_id)
            await session.commit()
            print(
                json.dumps(
                    {
                        "event": "source_discovery",
                        "source_id": str(job.source_id),
                        "links_seen": discovery_outcome.links_seen,
                        "created": discovery_outcome.created,
                        "skipped_known": discovery_outcome.skipped_known,
                    }
                ),
                flush=True,
            )
        return
    if job.kind == JobKind.sheets_sync:
        from app.services.sheets import process_sheets_outbox

        async with async_session_factory() as session:
            result = await process_sheets_outbox(session)
            await session.commit()
            print(json.dumps({"event": "sheets_sync", **result}), flush=True)
        return
    if job.kind == JobKind.deliver_alert:
        from app.services.alerts import deliver_pending_alerts

        async with async_session_factory() as session:
            result = await deliver_pending_alerts(session)
            await session.commit()
            print(json.dumps({"event": "deliver_alerts", **result}), flush=True)
        return
    if job.kind == JobKind.rescore:
        from app.db.models.opportunity import Opportunity, OpportunityRevision
        from app.services.assessment import assess_opportunity, get_or_create_profile

        payload = job.payload_json or {}
        raw_id = payload.get("opportunity_id")
        if not raw_id:
            raise ValueError("rescore job has no opportunity_id")
        opportunity_id = uuid.UUID(str(raw_id))
        async with async_session_factory() as session:
            opportunity = await session.get(Opportunity, opportunity_id)
            if opportunity is None:
                raise ValueError("rescore opportunity no longer exists")
            profile = await get_or_create_profile(session)
            revision_id = await session.scalar(
                select(OpportunityRevision.id)
                .where(OpportunityRevision.opportunity_id == opportunity.id)
                .order_by(OpportunityRevision.revision_number.desc())
                .limit(1)
            )
            assessment, _ = await assess_opportunity(session, opportunity, profile, revision_id)
            await session.commit()
            print(
                json.dumps(
                    {
                        "event": "rescore",
                        "opportunity_id": str(opportunity.id),
                        "assessment_id": str(assessment.id),
                        "score": assessment.score_total,
                    }
                ),
                flush=True,
            )
        return
    if job.kind == JobKind.generate_digest:
        from app.db.models.enums import DigestKind
        from app.services.digests import generate_digest

        payload_kind = (job.payload_json or {}).get("kind", "daily")
        digest_kind = DigestKind.weekly if payload_kind == "weekly" else DigestKind.daily
        async with async_session_factory() as session:
            digest, created = await generate_digest(session, digest_kind)
            await session.commit()
            print(
                json.dumps(
                    {
                        "event": "generate_digest",
                        "digest_id": str(digest.id),
                        "kind": digest_kind.value,
                        "created": created,
                        "opportunities": len(digest.opportunity_ids or []),
                    }
                ),
                flush=True,
            )
        return
    raise ValueError(f"Unsupported job kind: {job.kind.value}")


async def run_once() -> int:
    processed = 0
    async with async_session_factory() as session:
        await recover_expired_jobs(session)
        await session.commit()
    while _running:
        async with async_session_factory() as session:
            if not _running:
                break
            # A claim already underway must commit and finish its job, even on shutdown.
            job = await claim_job(session, WORKER_ID)
            await session.commit()
        if job is None:
            break
        processed += 1
        try:
            await process_job(job)
        except Exception as exc:
            async with async_session_factory() as session:
                current = await session.get(Job, job.id)
                if current is not None:
                    await fail_job(session, current, f"{type(exc).__name__}: {str(exc)[:500]}")
                    await session.commit()
            print(
                json.dumps(
                    {
                        "event": "job_failed",
                        "job_id": str(job.id),
                        "kind": job.kind.value,
                        "error": type(exc).__name__,
                    }
                ),
                flush=True,
            )
            continue
        async with async_session_factory() as session:
            current = await session.get(Job, job.id)
            if current is not None:
                await complete_job(session, current)
                await session.commit()
    return processed


async def run_forever() -> None:
    wakeup = asyncio.Event()
    _install_signal_handlers(wakeup)
    print(json.dumps({"event": "worker_started", "worker_id": WORKER_ID}), flush=True)
    while _running:
        processed = await run_once()
        if processed == 0 and _running:
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=2.0)
            except TimeoutError:
                pass
    print(json.dumps({"event": "worker_stopped", "worker_id": WORKER_ID}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="DiscMon ingestion worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain currently available jobs and exit",
    )
    args = parser.parse_args()
    if args.once:
        run(run_once())
    else:
        run(run_forever())


if __name__ == "__main__":
    main()
