from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import scheduler
from app.collectors import http as collector_http
from app.collectors.http import FetchPolicy, SafeFetcher
from app.db.models.audit import AuditEvent
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import JobKind, JobState, SourceKind
from app.db.models.job import Job
from app.db.models.opportunity import Opportunity
from app.db.models.source import Source
from app.db.session import async_session_factory, get_db
from app.main import app
from app.services import discovery, queue
from app.worker import process_job
from tests.factories import make_source

SOURCE_URL = "https://example.org/programmes"


class OfflineDiscoveryHTTP:
    def __init__(self) -> None:
        self.body = b""
        self.status_code = 200
        self.requests: list[str] = []

    async def respond(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        assert request.method == "GET"
        assert url == SOURCE_URL
        return httpx.Response(
            self.status_code, content=self.body, headers={"content-type": "text/html"}
        )


def programmes_page(*, include_new: bool = False) -> bytes:
    new_link = '<a href="/programmes/new">New programme</a>' if include_new else ""
    return f"""<!doctype html>
    <html><body>
      <a href="/programmes/one">Official programme</a>
      <a href="https://example.org/programmes/one?utm_source=directory">Tracked duplicate</a>
      <a href="https://partner.example.org/programmes/two">Partner programme</a>
      <a href="https://outside.invalid/programmes/no">External link</a>
      <a href="javascript:alert(1)">Malformed link</a>
      <a href="https://user:secret@example.org/programmes/private">Credential URL</a>
      {new_link}
    </body></html>""".encode()


@pytest.fixture
def offline_discovery_http(monkeypatch: pytest.MonkeyPatch) -> OfflineDiscoveryHTTP:
    boundary = OfflineDiscoveryHTTP()

    async def resolve(host: str, port: int) -> list[str]:
        assert host == "example.org" and port == 443
        return ["93.184.216.34"]

    monkeypatch.setattr(collector_http, "_resolve_host", resolve)

    class OfflineSafeFetcher(SafeFetcher):
        def __init__(self, policy: FetchPolicy) -> None:
            self.client = httpx.AsyncClient(transport=httpx.MockTransport(boundary.respond))
            super().__init__(policy, client=self.client)

        async def close(self) -> None:
            await self.client.aclose()

    monkeypatch.setattr(discovery, "SafeFetcher", OfflineSafeFetcher)
    return boundary


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http
    app.dependency_overrides.clear()


@pytest.mark.integration
async def test_monthly_discovery_stays_pending_until_owner_review(
    client: httpx.AsyncClient,
    session: AsyncSession,
    offline_discovery_http: OfflineDiscoveryHTTP,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = [datetime(2026, 11, 1, 3, 30, tzinfo=UTC)]

    def frozen_now() -> datetime:
        return clock[0]

    monkeypatch.setattr(scheduler, "now_utc", frozen_now)
    monkeypatch.setattr(queue, "now_utc", frozen_now)
    monkeypatch.setattr(discovery, "now_utc", frozen_now)

    source = await make_source(
        session,
        name="Synthetic programmes directory",
        kind=SourceKind.static_html,
        url=SOURCE_URL,
        config={
            "discovery": {
                "enabled": True,
                "cadence": "monthly",
                "allowed_domains": ["example.org"],
                "max_candidates": 10,
            }
        },
    )
    source.next_due_at = datetime(2099, 1, 1, tzinfo=UTC)
    await session.commit()

    async def run_month(month: str, body: bytes) -> tuple[str, dict[str, Any]]:
        offline_discovery_http.body = body
        scheduled = await scheduler.schedule_once()
        key = f"discover:monthly:{source.id}:{month}"
        job = await session.scalar(select(Job).where(Job.idempotency_key == key))
        assert job is not None and job.kind == JobKind.discover_source
        assert job.state == JobState.queued and job.source_id == source.id
        assert job.available_at == clock[0]
        assert str(job.id) in scheduled["discovery_jobs"]

        # Keep unrelated scheduler jobs queued, not processed by this test.
        await session.execute(
            update(Job)
            .where(Job.kind != JobKind.discover_source)
            .values(available_at=clock[0] + timedelta(days=1))
        )
        await session.commit()

        claimed = await queue.claim_job(session, f"monthly-discovery-{month}")
        assert claimed is not None and claimed.id == job.id
        assert claimed.kind == JobKind.discover_source and claimed.state == JobState.running
        await session.commit()
        await process_job(claimed)
        worker_event = json.loads(capsys.readouterr().out.strip())

        async with async_session_factory() as worker_session:
            completed = await worker_session.get(Job, job.id)
            assert completed is not None and completed.state == JobState.running
            await queue.complete_job(worker_session, completed)
            await worker_session.commit()
            assert completed.state == JobState.succeeded

        return str(job.id), worker_event

    first_job_id, first_worker = await run_month("2026-11", programmes_page())
    assert first_worker == {
        "event": "source_discovery",
        "source_id": str(source.id),
        "links_seen": 6,
        "created": 2,
        "skipped_known": 0,
    }
    first_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == "discovery.scanned",
            AuditEvent.entity_id == source.id,
        )
    )
    assert first_audit is not None
    assert first_audit.after_json == {
        "links_seen": 6,
        "created": 2,
        "skipped_known": 0,
        "skipped_invalid": 3,
    }
    assert offline_discovery_http.requests == [SOURCE_URL]

    response = await client.get("/v1/discovery/candidates")
    assert response.status_code == 200
    first_rows = {row["url"]: row for row in response.json()["items"]}
    official_url = "https://example.org/programmes/one"
    partner_url = "https://partner.example.org/programmes/two"
    assert set(first_rows) == {official_url, partner_url}
    for url, row in first_rows.items():
        assert row["approval_status"] == "candidate"
        assert row["legal_review_status"] == "pending"
        assert row["promoted_source_id"] is None
        assert row["notes"] == (
            "Discovered from approved source Synthetic programmes directory; "
            "review before enabling."
        )
        candidate = await session.get(DiscoveryCandidate, row["id"])
        assert candidate is not None and candidate.found_via_source_id == source.id
        assert candidate.candidate_url == url
    assert first_rows[official_url]["officialness_guess"] == "official"
    assert first_rows[partner_url]["officialness_guess"] == "unknown"

    official_id = first_rows[official_url]["id"]
    denied = await client.post(f"/v1/discovery/candidates/{official_id}/promote")
    assert denied.status_code == 400

    approved = await client.post(
        f"/v1/discovery/candidates/{official_id}/decision",
        json={"decision": "approved"},
    )
    assert approved.status_code == 200
    promoted = await client.post(f"/v1/discovery/candidates/{official_id}/promote")
    assert promoted.status_code == 201
    promoted_body = promoted.json()
    assert promoted_body["created"] is True
    promoted_source = await session.get(Source, promoted_body["source_id"])
    assert promoted_source is not None
    assert promoted_source.root_url == official_url
    assert promoted_source.approval_status.value == "approved"
    assert promoted_source.enabled is False
    assert promoted_source.legal_review_status.value == "pending"
    repeated = await client.post(f"/v1/discovery/candidates/{official_id}/promote")
    assert repeated.status_code == 201
    assert repeated.json()["created"] is False
    assert repeated.json()["source_id"] == promoted_body["source_id"]

    clock[0] = datetime(2026, 11, 22, 0, 0, tzinfo=UTC)
    await scheduler.schedule_once()
    monthly_jobs = (
        await session.scalars(select(Job).where(Job.kind == JobKind.discover_source))
    ).all()
    assert len(monthly_jobs) == 1 and str(monthly_jobs[0].id) == first_job_id
    assert offline_discovery_http.requests == [SOURCE_URL]

    clock[0] = datetime(2026, 12, 1, 3, 30, tzinfo=UTC)
    second_job_id, second_worker = await run_month("2026-12", programmes_page(include_new=True))
    assert second_job_id != first_job_id
    assert second_worker == {
        "event": "source_discovery",
        "source_id": str(source.id),
        "links_seen": 7,
        "created": 1,
        "skipped_known": 2,
    }
    scan_events = (
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "discovery.scanned",
                AuditEvent.entity_id == source.id,
            )
            .order_by(AuditEvent.timestamp)
        )
    ).all()
    assert len(scan_events) == 2
    assert {event.after_json["created"]: event.after_json for event in scan_events} == {
        2: {
            "links_seen": 6,
            "created": 2,
            "skipped_known": 0,
            "skipped_invalid": 3,
        },
        1: {
            "links_seen": 7,
            "created": 1,
            "skipped_known": 2,
            "skipped_invalid": 3,
        },
    }

    response = await client.get("/v1/discovery/candidates")
    assert response.status_code == 200
    final_rows = {row["url"]: row for row in response.json()["items"]}
    new_url = "https://example.org/programmes/new"
    assert set(final_rows) == {official_url, partner_url, new_url}
    assert final_rows[official_url]["approval_status"] == "approved"
    assert final_rows[official_url]["promoted_source_id"] == promoted_body["source_id"]
    assert final_rows[partner_url]["approval_status"] == "candidate"
    assert final_rows[new_url]["approval_status"] == "candidate"
    assert all(row["legal_review_status"] == "pending" for row in final_rows.values())
    new_candidate = await session.get(DiscoveryCandidate, final_rows[new_url]["id"])
    assert new_candidate is not None and new_candidate.found_via_source_id == source.id
    assert await session.scalar(select(Opportunity.id).limit(1)) is None
    before_failure = {
        url: (row["approval_status"], row["promoted_source_id"]) for url, row in final_rows.items()
    }

    sentinel = Opportunity(
        title="Existing synthetic opportunity",
        official_url="https://example.org/existing-opportunity",
        first_seen_at=clock[0],
        last_seen_at=clock[0],
    )
    session.add(sentinel)
    await session.commit()
    sentinel_state = sentinel.life_state

    clock[0] = datetime(2027, 1, 1, 3, 30, tzinfo=UTC)
    offline_discovery_http.status_code = 400
    failed_schedule = await scheduler.schedule_once()
    failed_key = f"discover:monthly:{source.id}:2027-01"
    failed_job = await session.scalar(select(Job).where(Job.idempotency_key == failed_key))
    assert failed_job is not None and failed_job.kind == JobKind.discover_source
    assert str(failed_job.id) in failed_schedule["discovery_jobs"]
    await session.execute(
        update(Job)
        .where(Job.kind != JobKind.discover_source)
        .values(available_at=clock[0] + timedelta(days=1))
    )
    await session.commit()
    failed_claim = await queue.claim_job(session, "monthly-discovery-2027-01")
    assert failed_claim is not None and failed_claim.id == failed_job.id
    assert failed_claim.kind == JobKind.discover_source and failed_claim.state == JobState.running
    await session.commit()
    with pytest.raises(RuntimeError, match="HTTP 400"):
        await process_job(failed_claim)
    async with async_session_factory() as worker_session:
        failed = await worker_session.get(Job, failed_job.id)
        assert failed is not None and failed.state == JobState.running
        await queue.fail_job(worker_session, failed, "Synthetic HTTP failure")
        await worker_session.commit()
        assert failed.state == JobState.retry_wait
        failed_state = failed.state.value

    response = await client.get("/v1/discovery/candidates")
    after_failure = {
        row["url"]: (row["approval_status"], row["promoted_source_id"])
        for row in response.json()["items"]
    }
    assert after_failure == before_failure
    await session.refresh(sentinel)
    assert sentinel.life_state == sentinel_state
    assert list((await session.scalars(select(Opportunity.id))).all()) == [sentinel.id]

    print(
        json.dumps(
            {
                "monthly_jobs": [
                    {"id": first_job_id, "key": f"discover:monthly:{source.id}:2026-11"},
                    {"id": second_job_id, "key": f"discover:monthly:{source.id}:2026-12"},
                ],
                "worker_counts": [first_worker, second_worker],
                "audit_counts": [event.after_json for event in scan_events],
                "ist_windows": ["2026-11-01T09:00:00+05:30", "2026-12-01T09:00:00+05:30"],
                "job_transitions": ["queued", "running", "succeeded"],
                "same_month_job_count": len(monthly_jobs),
                "existing_opportunity_preserved": str(sentinel.id),
                "failed_job": {"id": str(failed_job.id), "state": failed_state},
                "candidates": [
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "approval": row["approval_status"],
                        "legal": row["legal_review_status"],
                        "promoted_source_id": row["promoted_source_id"],
                    }
                    for row in final_rows.values()
                ],
                "promotion": {
                    "denied_before_approval": denied.status_code,
                    "created": promoted_body["created"],
                    "repeat_created": repeated.json()["created"],
                },
                "http_requests": offline_discovery_http.requests,
            },
            sort_keys=True,
        ),
        flush=True,
    )
