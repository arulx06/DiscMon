from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import http as collector_http
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
    SourceKind,
)
from app.db.models.evidence import RawEvidence
from app.db.models.job import Job
from app.db.models.opportunity import (
    Opportunity,
    OpportunityRevision,
    OpportunitySource,
    Organization,
)
from app.db.models.source import Source, SourceRun
from app.db.models.sync import SyncOutbox
from app.db.session import async_session_factory
from app.main import app
from app.services.queue import claim_job, complete_job, enqueue_source_job, fail_job
from app.worker import process_job
from tests.factories import make_source

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parent / "fixtures" / "github_watch"
API_URL = "https://api.github.com/repos/example/engineering-programmes/releases?per_page=30"
OFFICIAL_URL = "https://github.com/example/engineering-programmes/releases/tag/engineering-2027"


@dataclass
class GitHubHTTP:
    body: bytes = field(default_factory=lambda: (FIXTURES / "releases_a.json").read_bytes())
    mode: str = "ok"
    requests: list[dict] = field(default_factory=list)

    async def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == API_URL
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2022-11-28"
        assert "authorization" not in request.headers
        status = {"403": 403, "429": 429, "503": 503, "redirect": 302}.get(self.mode, 200)
        self.requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "status": None if self.mode == "transport" else status,
            }
        )
        if self.mode == "transport":
            raise httpx.ConnectError("Synthetic offline boundary", request=request)
        body = {"malformed": b"{", "shape": b'{"message":"not a list"}', "bad_item": b"[null]"}.get(
            self.mode, self.body
        )
        headers = {"content-type": "application/json", "retry-after": "0.01"}
        if self.mode == "redirect":
            headers["location"] = "https://169.254.169.254/latest/meta-data/"
        return httpx.Response(status, content=body, headers=headers)


@pytest.fixture
def github_http(monkeypatch):
    boundary = GitHubHTTP()

    async def handle(_transport, request):
        return await boundary.respond(request)

    async def resolve(host, port):
        assert host == "api.github.com" and port == 443
        return ["93.184.216.34"]

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setattr(collector_http, "_resolve_host", resolve)
    monkeypatch.setenv("SHEETS_SYNC_ENABLED", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert not any(
        (
            settings.github_token,
            settings.telegram_enabled,
            settings.smtp_enabled,
            settings.sheets_configured,
            settings.ai_enabled,
            settings.allow_private_fetch_hosts,
        )
    )
    yield boundary
    get_settings.cache_clear()


async def source_for(session: AsyncSession) -> Source:
    source = await make_source(
        session,
        kind=SourceKind.github,
        name="example releases",
        url="https://github.com/example/engineering-programmes",
        config={
            "repos": ["example/engineering-programmes"],
            "mode": "releases",
            "license_note": "Synthetic permitted GitHub fixture",
        },
    )
    source.rate_limit_json = {"per_minute": 0}
    await session.commit()
    return source


async def request_run(source_id: uuid.UUID) -> uuid.UUID:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(f"/v1/sources/{source_id}/run")
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["job_id"])


async def execute(source_id: uuid.UUID) -> uuid.UUID:
    job_id = await request_run(source_id)
    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None and job.state == JobState.queued
        job = await claim_job(session, "task14-worker")
        assert job is not None and job.id == job_id and job.source_id == source_id
        assert job.kind == JobKind.ingest_source and job.state == JobState.running
        await session.commit()
    await process_job(job)
    async with async_session_factory() as session:
        stored = await session.get(Job, job_id)
        await complete_job(session, stored)
        await session.commit()
        assert stored.state == JobState.succeeded
    print(json.dumps({"job_id": str(job_id), "states": ["queued", "running", "succeeded"]}))
    return job_id


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


async def snapshot(session, opportunity, version, revision_number, job_id):
    expected_body = (FIXTURES / f"releases_{version}.json").read_bytes()
    release = json.loads(expected_body)[0]
    revision = await session.get(OpportunityRevision, opportunity.current_revision_id)
    assert revision.revision_number == revision_number
    assert opportunity.provider_key == "github:example/engineering-programmes:releases:14001"
    assert opportunity.provider_source_kind == SourceKind.github
    assert opportunity.official_url == OFFICIAL_URL and opportunity.application_url is None
    assert opportunity.deadline_on == date(2027, 3, 12 if version == "a" else 19)
    assert opportunity.deadline_precision == DeadlinePrecision.date_only
    assert opportunity.deadline_at is None and opportunity.deadline_timezone is None
    assert opportunity.professional_eligibility == EligibilityStatus.verified_yes
    assert opportunity.india_eligibility == EligibilityStatus.verified_yes
    organization = await session.get(Organization, opportunity.organization_id)
    assert organization.canonical_name == "example"
    evidence = await session.get(RawEvidence, uuid.UUID(revision.evidence_ids[0]))
    run = await session.get(SourceRun, revision.source_run_id)
    assert run.job_id == job_id and run.status == "success" and not run.scan_complete
    assert run.snapshot_hash == hashlib.sha256(expected_body).hexdigest()
    assert evidence.source_run_id == run.id and evidence.source_id == run.source_id
    assert evidence.canonical_url == OFFICIAL_URL
    assert evidence.content_json["source_payload"]["item"] == release
    assert evidence.content_json["source_external_id"] == "14001"
    assert evidence.content_json["source_payload"]["repo"] == "example/engineering-programmes"
    assert evidence.content_json["source_payload"]["tag_name"] == "engineering-2027"
    serialized = json.dumps(
        evidence.content_json, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    assert evidence.content_hash == hashlib.sha256(serialized.encode()).hexdigest()
    assessment = await session.scalar(
        select(Assessment).order_by(Assessment.created_at.desc()).limit(1)
    )
    assert assessment.revision_id == revision.id and not assessment.is_ai_assisted
    assert assessment.professional_eligibility_state == EligibilityStatus.verified_yes
    assert assessment.india_eligibility_state == EligibilityStatus.verified_yes
    assert assessment.evidence_refs_json[0]["content_hash"] == evidence.content_hash
    assert assessment.hard_gate_status.value == "passed"
    assert 94 <= assessment.score_total <= 100
    assert assessment.recommended_bucket.value == "act_now"
    print(
        json.dumps(
            {
                "opportunity_id": str(opportunity.id),
                "revision_id": str(revision.id),
                "source_run_id": str(run.id),
                "evidence_id": str(evidence.id),
                "evidence_hash": evidence.content_hash,
                "snapshot_hash": run.snapshot_hash,
                "deadline": str(opportunity.deadline_on),
                "assessment_id": str(assessment.id),
                "score": assessment.score_total,
                "hard_gate": assessment.hard_gate_status.value,
                "bucket": assessment.recommended_bucket.value,
            }
        )
    )
    return revision


async def test_release_watch_revision_and_unchanged(session, github_http):
    source = await source_for(session)
    assert source.enabled and source.approval_status == ApprovalStatus.approved
    assert source.legal_review_status == LegalReviewStatus.approved
    source_id = source.id
    first_job = await execute(source_id)
    opportunity = await session.scalar(select(Opportunity))
    opportunity_id = opportunity.id
    first = await snapshot(session, opportunity, "a", 1, first_job)
    first_id = first.id
    assert await count(session, Alert) == 1
    await session.commit()
    github_http.body = (FIXTURES / "releases_b.json").read_bytes()
    second_job = await execute(source_id)
    assert second_job != first_job
    session.expire_all()
    opportunity = await session.get(Opportunity, opportunity_id)
    second = await snapshot(session, opportunity, "b", 2, second_job)
    second_id = second.id
    assert second.material_diff_json["deadline_on"] == {"old": "2027-03-12", "new": "2027-03-19"}
    await session.commit()
    for _ in range(3):
        await execute(source_id)
    session.expire_all()
    assert await count(session, Opportunity) == await count(session, OpportunitySource) == 1
    assert await count(session, OpportunityRevision) == 2
    assert await count(session, Assessment) == 5
    alerts = list((await session.scalars(select(Alert))).all())
    assert len(alerts) == len({a.dedup_key for a in alerts}) == 2
    assert {a.revision_id for a in alerts} == {first_id, second_id}
    assert all(a.alert_kind.value == "immediate" for a in alerts)
    assert {a.payload_json["deadline_on"] for a in alerts} == {"2027-03-12", "2027-03-19"}
    assert all(94 <= a.payload_json["score"] <= 100 for a in alerts)
    assert all(a.channel == "in_app" and a.status.value == "pending" for a in alerts)
    assert await count(session, SyncOutbox) == 1
    outbox = await session.scalar(select(SyncOutbox))
    assert outbox.status.value == "pending" and outbox.retries == 0
    link = await session.scalar(select(OpportunitySource))
    assert link.absence_count == 0
    opportunity = await session.get(Opportunity, opportunity_id)
    assert opportunity.life_state == LifeState.open and opportunity.current_revision_id == second_id
    runs = list((await session.scalars(select(SourceRun).order_by(SourceRun.started_at))).all())
    assert [r.records_skipped for r in runs] == [0, 0, 1, 1, 1]
    assert all(r.status == "success" and not r.scan_complete for r in runs)
    assert len(github_http.requests) == 5
    print(
        json.dumps(
            {
                "requests": github_http.requests,
                "opportunities": 1,
                "revisions": 2,
                "alerts": 2,
                "outbox": 1,
                "assessments": 5,
            }
        )
    )


@pytest.mark.parametrize(
    "mode", ["403", "429", "503", "transport", "malformed", "shape", "bad_item", "redirect"]
)
async def test_failed_watch_preserves_canonical(session, github_http, mode):
    source = await source_for(session)
    source_id = source.id
    await execute(source_id)
    opportunity = await session.scalar(select(Opportunity))
    opportunity_id, revision_id = opportunity.id, opportunity.current_revision_id
    await session.commit()
    github_http.mode = mode
    for _ in range(3):
        await execute(source_id)
    session.expire_all()
    source = await session.get(Source, source_id)
    assert source.consecutive_failures == 3 and source.health_status == HealthStatus.stale
    assert source.last_error_category
    runs = list(
        (await session.scalars(select(SourceRun).where(SourceRun.status == "failed"))).all()
    )
    assert len(runs) == 3 and all(not r.scan_complete and r.error_category for r in runs)
    expected_error = {
        "403": "http_error",
        "429": "http_error",
        "503": "http_error",
        "transport": "network_error",
        "malformed": "invalid_response",
        "shape": "invalid_response",
        "bad_item": "invalid_response",
        "redirect": "host_not_allowed",
    }[mode]
    assert all(r.error_category == expected_error for r in runs)
    opportunity = await session.get(Opportunity, opportunity_id)
    assert (
        opportunity.current_revision_id == revision_id and opportunity.life_state == LifeState.open
    )
    assert await count(session, OpportunityRevision) == await count(session, OpportunitySource) == 1
    assert await count(session, Alert) == await count(session, SyncOutbox) == 1
    link = await session.scalar(select(OpportunitySource))
    assert link.absence_count == 0
    print(
        json.dumps(
            {
                "mode": mode,
                "errors": [r.error_category for r in runs],
                "requests": github_http.requests,
                "canonical_preserved": True,
            }
        )
    )


@pytest.mark.parametrize("gate", ["disabled", "unapproved", "legal"])
async def test_source_gate_rechecked_by_worker(session, github_http, gate):
    source = await source_for(session)
    source_id = source.id
    job_id = await request_run(source_id)
    if gate == "disabled":
        source.enabled = False
    elif gate == "unapproved":
        source.approval_status = ApprovalStatus.candidate
    else:
        source.legal_review_status = LegalReviewStatus.pending
    await session.commit()
    async with async_session_factory() as worker_session:
        job = await claim_job(worker_session, "task14-gate-worker")
        assert job.id == job_id
        await worker_session.commit()
    with pytest.raises(ValueError, match="disabled|approval and legal review"):
        await process_job(job)
    async with async_session_factory() as worker_session:
        stored = await worker_session.get(Job, job_id)
        await fail_job(worker_session, stored, "Source gate revoked")
        await worker_session.commit()
        assert stored.state == JobState.retry_wait
    assert github_http.requests == []
    assert await count(session, Opportunity) == await count(session, SourceRun) == 0


async def test_github_concurrent_enqueue_and_active_states(session, github_http):
    source = await source_for(session)
    source_id = source.id
    other = await source_for(session)
    other_id = other.id
    await session.commit()

    async def enqueue():
        async with async_session_factory() as own:
            result = await enqueue_source_job(own, source_id)
            await own.commit()
            return result

    results = await asyncio.gather(*(enqueue() for _ in range(8)))
    assert sum(r is not None for r in results) == 1
    job = await session.get(Job, next(r for r in results if r is not None))
    for state in (JobState.queued, JobState.running, JobState.retry_wait):
        job.state = state
        await session.commit()
        assert await enqueue() is None
    assert await enqueue_source_job(session, other_id) is not None
    job.state = JobState.succeeded
    await session.commit()
    assert await enqueue() not in (None, job.id)
    assert github_http.requests == []


@pytest.mark.parametrize(
    ("body", "professional", "india", "hard_gate"),
    [
        (
            "Open to working professionals. Remote programme.",
            "verified_yes",
            "unknown",
            "needs_verification",
        ),
        (
            "Students only. Residents of India are eligible.",
            "verified_no",
            "verified_yes",
            "excluded",
        ),
    ],
)
async def test_connected_conservative_hard_gates(
    session, github_http, body, professional, india, hard_gate
):
    release = json.loads(github_http.body)[0]
    release["body"] = body + " Application deadline: 12 March 2027."
    github_http.body = json.dumps([release]).encode()
    source = await source_for(session)
    await execute(source.id)
    opportunity = await session.scalar(select(Opportunity))
    assessment = await session.scalar(select(Assessment))
    assert opportunity.professional_eligibility.value == professional
    assert opportunity.india_eligibility.value == india
    assert assessment.hard_gate_status.value == hard_gate
    assert not assessment.is_ai_assisted
    assert await count(session, Alert) == 0
    assert await count(session, OpportunityRevision) == 1
    assert await count(session, SyncOutbox) == 1
