from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.enums import (
    ApprovalStatus,
    DeadlinePrecision,
    EligibilityStatus,
    HealthStatus,
    JobKind,
    JobState,
    LegalReviewStatus,
    LifeState,
    RevisionType,
    SourceKind,
    SyncStatus,
)
from app.db.models.evidence import RawEvidence
from app.db.models.job import Job
from app.db.models.opportunity import Opportunity, OpportunityRevision, OpportunitySource
from app.db.models.source import Source, SourceRun
from app.db.models.sync import SyncOutbox
from app.db.models.webhook import WebhookEvent
from app.db.session import async_session_factory
from app.main import app
from app.services.ingestion import ingest_source
from app.services.queue import claim_job, complete_job, enqueue_source_job, fail_job
from app.services.time import now_utc
from app.worker import process_job
from tests.factories import make_source

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parent / "fixtures" / "changedetection"
OFFICIAL_URL = "https://93.184.216.34/fellowship"
ATTACKER_URL = "http://169.254.169.254/latest/meta-data/"
WATCH = "89ce954e-b6ba-4a30-ac39-394620b64c01"
SECRET = "task13-synthetic-webhook-secret"
ENDPOINT = "/v1/integrations/changedetection/webhook"


@dataclass
class OfficialHTTP:
    body: bytes = field(default_factory=lambda: (FIXTURES / "fellowship_a.html").read_bytes())
    mode: str = "ok"
    requests: list[str] = field(default_factory=list)

    async def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        assert str(request.url) == OFFICIAL_URL, "Unexpected outbound HTTP target"
        if self.mode == "failure":
            raise httpx.ConnectError("Synthetic offline failure", request=request)
        if self.mode == "redirect":
            return httpx.Response(302, headers={"location": ATTACKER_URL})
        return httpx.Response(200, content=self.body, headers={"content-type": "text/html"})


@pytest.fixture
def official_http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[OfficialHTTP]:
    # A public IP literal keeps the real SSRF checks without external DNS traffic.
    official = OfficialHTTP()

    async def handle(_transport, request: httpx.Request) -> httpx.Response:
        return await official.respond(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setenv("CHANGEDETECTION_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SHEETS_SYNC_ENABLED", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert not settings.allow_private_fetch_hosts
    assert not settings.telegram_enabled and not settings.smtp_enabled
    assert not settings.sheets_configured and not settings.ai_enabled
    yield official
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(official_http: OfficialHTTP) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http


async def watched_source(session: AsyncSession) -> Source:
    source = await make_source(
        session,
        name="Synthetic Engineering Foundation",
        kind=SourceKind.changedetection,
        url=OFFICIAL_URL,
        config={"watch_uuid": WATCH, "remote": True, "license_note": "Synthetic permitted fixture"},
    )
    source.rate_limit_json = {"per_minute": 0}
    await session.commit()
    return source


async def signed_event(client: httpx.AsyncClient, **payload) -> httpx.Response:
    body = json.dumps({"watch_uuid": WATCH, **payload}, sort_keys=True).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return await client.post(
        ENDPOINT, content=body, headers={"x-changedetection-signature": f"sha256={signature}"}
    )


async def count(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def execute_source_job(source_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        job = await claim_job(session, "task13-worker")
        assert job is not None and job.kind == JobKind.ingest_source
        assert job.source_id == source_id and job.state == JobState.running
        await session.commit()
    await process_job(job)
    async with async_session_factory() as session:
        stored = await session.get(Job, job.id)
        assert stored is not None
        await complete_job(session, stored)
        await session.commit()
        assert stored.state == JobState.succeeded
    return job.id


async def assert_revision(
    session: AsyncSession, opportunity: Opportunity, number: int, deadline: date
) -> OpportunityRevision:
    revision = await session.get(OpportunityRevision, opportunity.current_revision_id)
    assert revision is not None and revision.revision_number == number
    assert revision.opportunity_id == opportunity.id
    assert revision.normalized_snapshot_json["deadline_on"] == deadline.isoformat()
    assert opportunity.deadline_on == deadline
    assert opportunity.deadline_precision == DeadlinePrecision.date_only
    assert opportunity.deadline_at is None and opportunity.deadline_timezone is None
    run = await session.get(SourceRun, revision.source_run_id)
    assert run is not None and run.status == "success" and not run.scan_complete
    assert len(revision.evidence_ids) == 1
    evidence = await session.get(RawEvidence, uuid.UUID(revision.evidence_ids[0]))
    assert evidence is not None and evidence.source_run_id == run.id
    assert evidence.source_id == run.source_id
    assert evidence.source_url == evidence.canonical_url == OFFICIAL_URL
    assert evidence.content_json is not None
    assert evidence.content_json["deadline_on"] == deadline.isoformat()
    assert evidence.content_json["deadline_at"] is None
    version = "a" if number == 1 else "b"
    page_hash = hashlib.sha256((FIXTURES / f"fellowship_{version}.html").read_bytes()).hexdigest()
    assert evidence.content_json["source_payload"]["page_hash"] == run.snapshot_hash == page_hash
    assert evidence.source_license_or_terms_note == "Synthetic permitted fixture"
    link = await session.scalar(select(OpportunitySource))
    assert link is not None and link.opportunity_id == opportunity.id
    assert link.source_id == run.source_id and link.raw_evidence_id == evidence.id
    assert link.absence_count == 0
    assessment = await session.scalar(
        select(Assessment).order_by(Assessment.created_at.desc()).limit(1)
    )
    assert assessment is not None and assessment.revision_id == revision.id
    assert assessment.professional_eligibility_state == opportunity.professional_eligibility
    assert assessment.india_eligibility_state == opportunity.india_eligibility
    assert assessment.evidence_refs_json[0]["url"] == OFFICIAL_URL
    assert assessment.evidence_refs_json[0]["content_hash"] == evidence.content_hash
    assert not assessment.is_ai_assisted
    return revision


async def test_signed_webhook_worker_material_revision_and_dedup(
    client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    source_id = source.id
    initial = await ingest_source(session, source_id)
    await session.commit()
    assert initial.status == "success" and initial.created == 1
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None and not opportunity.is_fixture
    opportunity_id = opportunity.id
    assert opportunity.professional_eligibility == EligibilityStatus.verified_yes
    assert opportunity.india_eligibility == EligibilityStatus.verified_yes
    first = await assert_revision(session, opportunity, 1, date(2099, 12, 15))
    first_revision_id = first.id
    assert first.revision_type == RevisionType.created
    assert await count(session, Assessment) == 1
    first_alert = await session.scalar(select(Alert))
    assert first_alert is not None and first_alert.revision_id == first.id
    assert first_alert.channel == "in_app" and first_alert.status.value == "pending"
    outbox = await session.scalar(select(SyncOutbox))
    assert outbox is not None and outbox.entity_id == opportunity_id
    outbox_id = outbox.id
    before = {
        "opportunity_id": str(opportunity_id),
        "revision_id": str(first.id),
        "revision_number": 1,
        "deadline_on": "2099-12-15",
        "alerts": 1,
        "outbox": 1,
    }
    await session.commit()

    response = await signed_event(client, watch_url=ATTACKER_URL, deadline_on="2100-01-01")
    assert response.status_code == 202 and response.json() == {"status": "queued"}
    duplicate = await signed_event(client, watch_url=ATTACKER_URL, deadline_on="2100-01-01")
    assert duplicate.json() == {"status": "duplicate"}
    repeated = await signed_event(client, event="different-body")
    assert repeated.json() == {"status": "already_queued"}
    assert await count(session, Job) == 1 and await count(session, WebhookEvent) == 2
    event = await session.scalar(select(WebhookEvent).where(WebhookEvent.status == "queued"))
    assert event is not None and event.source_id == source.id and event.watch_url == ATTACKER_URL
    queued_id = event.job_id
    assert await count(session, OpportunityRevision) == 1
    assert await count(session, RawEvidence) == 1
    assert opportunity.deadline_on == date(2099, 12, 15)
    assert official_http.requests == [OFFICIAL_URL]
    await session.commit()

    official_http.body = (FIXTURES / "fellowship_b.html").read_bytes()
    assert await execute_source_job(source_id) == queued_id
    session.expire_all()
    opportunity = await session.get(Opportunity, opportunity_id)
    assert opportunity is not None
    second = await assert_revision(session, opportunity, 2, date(2099, 12, 22))
    assert second.revision_type == RevisionType.updated
    assert second.material_diff_json["deadline_on"] == {"old": "2099-12-15", "new": "2099-12-22"}
    run = await session.get(SourceRun, second.source_run_id)
    assert run is not None and run.job_id == queued_id
    assert await count(session, Opportunity) == 1 and await count(session, OpportunityRevision) == 2
    alerts = list((await session.scalars(select(Alert))).all())
    assert len(alerts) == 2 and len({alert.dedup_key for alert in alerts}) == 2
    assert {alert.revision_id for alert in alerts} == {first_revision_id, second.id}
    assert all(alert.channel == "in_app" and alert.status.value == "pending" for alert in alerts)
    assert await count(session, SyncOutbox) == 1
    outbox = await session.get(SyncOutbox, outbox_id)
    assert outbox is not None and outbox.status == SyncStatus.pending and outbox.retries == 0
    await session.commit()

    after = {
        "opportunity_id": str(opportunity_id),
        "revision_id": str(second.id),
        "revision_number": 2,
        "deadline_on": "2099-12-22",
        "alerts": 2,
        "outbox": 1,
        "job_id": str(queued_id),
        "source_run_id": str(second.source_run_id),
        "evidence_ids": second.evidence_ids,
    }
    for index in range(3):
        unchanged = await signed_event(client, event=f"unchanged-{index}")
        assert unchanged.json() == {"status": "queued"}
        await execute_source_job(source_id)
    session.expire_all()
    assert await count(session, OpportunityRevision) == 2
    assert await count(session, Alert) == 2 and await count(session, SyncOutbox) == 1
    assert await count(session, Assessment) == 5
    runs = list((await session.scalars(select(SourceRun))).all())
    assert sorted(run.records_skipped for run in runs) == [0, 0, 1, 1, 1]
    assert all(not run.scan_complete for run in runs)
    link = await session.scalar(select(OpportunitySource))
    assert link is not None and link.absence_count == 0
    opportunity = await session.get(Opportunity, opportunity_id)
    assert opportunity is not None and opportunity.life_state == LifeState.open
    assert official_http.requests == [OFFICIAL_URL] * 5
    replay = await signed_event(client, watch_url=ATTACKER_URL, deadline_on="2100-01-01")
    assert replay.json() == {"status": "duplicate"}
    assert await count(session, Job) == 4 and await count(session, WebhookEvent) == 5
    print(
        json.dumps(
            {
                "before": before,
                "after": after,
                "unchanged_scans": 3,
                "revisions": 2,
                "assessments": 5,
                "alerts": 2,
                "outbox": 1,
                "http_requests": official_http.requests,
            },
            sort_keys=True,
        )
    )


@pytest.mark.parametrize("case", ["signature", "secret", "watch"])
async def test_authentication_and_unknown_watch_fail_closed(
    case: str,
    client: httpx.AsyncClient,
    session: AsyncSession,
    official_http: OfficialHTTP,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await watched_source(session)
    if case == "signature":
        response = await client.post(
            ENDPOINT, json={"watch_uuid": WATCH}, headers={"x-changedetection-signature": "bad"}
        )
        assert response.status_code == 401
    elif case == "secret":
        monkeypatch.delenv("CHANGEDETECTION_WEBHOOK_SECRET")
        get_settings.cache_clear()
        response = await signed_event(client)
        assert response.status_code == 503
    else:
        response = await signed_event(client, watch_uuid="unknown-watch")
        assert response.status_code == 202 and response.json() == {"status": "ignored"}
        event = await session.scalar(select(WebhookEvent))
        assert event is not None and event.source_id is None and event.job_id is None
    assert await count(session, Job) == 0
    assert await count(session, Opportunity) == 0
    assert await count(session, WebhookEvent) == (1 if case == "watch" else 0)
    assert official_http.requests == []


@pytest.mark.parametrize("gate", ["disabled", "unapproved", "legal_pending"])
async def test_source_gates_at_webhook_and_worker(
    gate: str, client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    accepted = await signed_event(client, event="before-revocation")
    assert accepted.json() == {"status": "queued"}
    if gate == "disabled":
        source.enabled = False
    elif gate == "unapproved":
        source.approval_status = ApprovalStatus.candidate
    else:
        source.legal_review_status = LegalReviewStatus.pending
    await session.commit()
    ignored = await signed_event(client, event="after-revocation")
    assert ignored.json() == {"status": "ignored"}
    assert await count(session, Job) == 1
    await session.commit()
    async with async_session_factory() as worker_session:
        job = await claim_job(worker_session, "revoked-source-worker")
        assert job is not None
        await worker_session.commit()
    with pytest.raises(ValueError, match="disabled|approval and legal review"):
        await process_job(job)
    assert await count(session, SourceRun) == 0
    assert await count(session, Opportunity) == 0
    assert official_http.requests == []


@pytest.mark.parametrize("mode", ["failure", "redirect", "empty"])
async def test_failed_fetches_preserve_records_and_report_source_failure(
    mode: str, client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    source_id = source.id
    initial = await ingest_source(session, source_id)
    assert initial.created == 1
    await session.commit()
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    opportunity_id, revision_id = opportunity.id, opportunity.current_revision_id
    await session.commit()
    official_http.mode = mode
    if mode == "empty":
        official_http.body = b""
    # Even three failed attempts cannot be counted as complete successful absences.
    for index in range(3):
        response = await signed_event(client, failure=index)
        assert response.json() == {"status": "queued"}
        await execute_source_job(source_id)
    source_id = source.id
    session.expire_all()
    opportunity = await session.get(Opportunity, opportunity_id)
    assert opportunity is not None and opportunity.current_revision_id == revision_id
    assert opportunity.life_state == LifeState.open
    assert opportunity.deadline_on == date(2099, 12, 15)
    assert await count(session, OpportunityRevision) == 1
    assert await count(session, Alert) == 1 and await count(session, SyncOutbox) == 1
    link = await session.scalar(select(OpportunitySource))
    assert link is not None and link.absence_count == 0
    source = await session.get(Source, source_id)
    assert source is not None and source.consecutive_failures == 3
    assert source.health_status != HealthStatus.healthy and source.last_error_redacted
    failed = list(
        (await session.scalars(select(SourceRun).where(SourceRun.status == "failed"))).all()
    )
    assert len(failed) == 3
    assert all(not run.scan_complete and run.error_category for run in failed)
    assert official_http.requests == [OFFICIAL_URL] * 4


async def test_missing_eligibility_is_not_inferred_from_remote(
    client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    source_id = source.id
    official_http.body = b"""<html><main><h1>Engineering Fellowship</h1>
    <p>Remote fellowship. Application deadline: 15 December 2099.</p>
    </main></html>"""
    assert (await signed_event(client)).json() == {"status": "queued"}
    await execute_source_job(source_id)
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    assert opportunity.professional_eligibility == EligibilityStatus.unknown
    assert opportunity.india_eligibility == EligibilityStatus.unknown
    assessment = await session.scalar(select(Assessment))
    assert assessment is not None and assessment.hard_gate_status.value == "needs_verification"
    assert await count(session, Alert) == 0
    assert await count(session, SyncOutbox) == 1


async def test_concurrent_signed_events_share_one_active_job(
    client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    source_id = source.id
    responses = await asyncio.gather(*(signed_event(client, event=index) for index in range(8)))
    assert all(response.status_code == 202 for response in responses)
    assert all(response.json()["status"] in {"queued", "already_queued"} for response in responses)
    assert await count(session, WebhookEvent) == 8
    assert await count(session, Job) == 1
    await session.commit()
    await execute_source_job(source_id)
    assert await count(session, OpportunityRevision) == 1
    assert official_http.requests == [OFFICIAL_URL]


async def test_overlapping_enqueue_across_timestamp_boundary_has_one_active_job(
    session: AsyncSession,
) -> None:
    source = await watched_source(session)
    stamp = now_utc()
    first_id = await enqueue_source_job(session, source.id, available_at=stamp)

    async def competing_enqueue() -> uuid.UUID | None:
        async with async_session_factory() as competitor:
            second_id = await enqueue_source_job(
                competitor, source.id, available_at=stamp + timedelta(seconds=1)
            )
            await competitor.commit()
            return second_id

    competing = asyncio.create_task(competing_enqueue())
    try:
        # Let the competing transaction reach the queue while the first is uncommitted.
        try:
            await asyncio.wait_for(asyncio.shield(competing), timeout=0.3)
        except TimeoutError:
            pass
        await session.commit()
        second_id = await asyncio.wait_for(competing, timeout=5)
    finally:
        if not competing.done():
            await session.rollback()
            competing.cancel()
            await asyncio.gather(competing, return_exceptions=True)
    assert first_id is not None
    assert second_id is None
    assert await count(session, Job) == 1


async def test_completed_job_can_be_enqueued_again_within_same_second(
    session: AsyncSession,
) -> None:
    source = await watched_source(session)
    stamp = now_utc()
    first_id = await enqueue_source_job(session, source.id, available_at=stamp)
    await session.commit()
    first = await claim_job(session, "same-second-worker")
    assert first is not None and first.id == first_id
    await complete_job(session, first)
    await session.commit()
    next_id = await enqueue_source_job(session, source.id, available_at=stamp)
    await session.commit()
    second = await session.get(Job, next_id)
    assert second is not None and second.id != first_id
    assert second.state == JobState.queued


@pytest.mark.parametrize("state", [JobState.running, JobState.retry_wait])
async def test_signed_event_does_not_duplicate_running_or_retrying_job(
    state: JobState, client: httpx.AsyncClient, session: AsyncSession, official_http: OfficialHTTP
) -> None:
    source = await watched_source(session)
    assert (await signed_event(client, event="first")).json() == {"status": "queued"}
    job = await claim_job(session, "active-job-worker")
    assert job is not None and job.source_id == source.id
    if state == JobState.retry_wait:
        await fail_job(session, job, "Synthetic retry")
    assert job.state == state
    await session.commit()
    repeat = await signed_event(client, event="second")
    assert repeat.json() == {"status": "already_queued"}
    assert await count(session, Job) == 1 and await count(session, WebhookEvent) == 2
    assert official_http.requests == []
