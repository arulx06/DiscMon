from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import webhooks
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import JobKind, SourceKind
from app.db.models.job import Job
from app.db.models.source import Source
from app.db.models.webhook import WebhookEvent
from app.db.session import get_db
from app.main import app as fastapi_app
from app.schemas.collector import FetchResult, SourceConfig
from app.services import discovery
from app.services.time import now_utc
from tests.factories import make_source


class DiscoveryAdapter:
    supports_closure = False

    def __init__(self, body: bytes) -> None:
        self.body = body

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        return {"example.com"}

    async def fetch(self, source: SourceConfig, fetcher, cursor=None) -> FetchResult:
        return FetchResult(
            source_id=source.id,
            fetched_at=now_utc(),
            http_status=200,
            content_type="text/html",
            raw_hash=hashlib.sha256(self.body).hexdigest(),
            raw_bytes=self.body,
            source_url=source.root_url,
        )

    def parse(self, source, result):
        return []


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    async def override_get_db():
        yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    fastapi_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_discovery_creates_deduped_candidates_and_promotes(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(
        session,
        name="Programme list",
        kind=SourceKind.static_html,
        url="https://example.com/programmes",
        config={
            "discovery": {
                "enabled": True,
                "allowed_domains": ["example.com"],
                "max_candidates": 10,
            }
        },
    )
    body = b"""
    <html><body>
      <a href="/programmes/one">Fellowship One</a>
      <a href="https://example.com/programmes/one?utm_source=test">Duplicate</a>
      <a href="https://blocked.example.net/programmes/two">Blocked</a>
      <a href="https://example.com/programmes">Root</a>
    </body></html>
    """
    adapter = DiscoveryAdapter(body)
    monkeypatch.setattr(discovery, "get_adapter", lambda kind: adapter)
    await session.commit()

    response = await client.post(f"/v1/discovery/sources/{source.id}/run")
    assert response.status_code == 202
    job = await session.scalar(
        select(Job).where(Job.kind == JobKind.discover_source)
    )
    assert job is not None

    outcome = await discovery.run_discovery(session, source.id)
    await session.commit()
    assert outcome.created == 1
    candidate = await session.scalar(select(DiscoveryCandidate))
    assert candidate is not None
    assert candidate.candidate_url == "https://example.com/programmes/one"
    assert candidate.promoted_source_id is None

    second = await discovery.run_discovery(session, source.id)
    await session.commit()
    assert second.created == 0
    assert second.skipped_known == 1

    decision = await client.post(
        f"/v1/discovery/candidates/{candidate.id}/decision",
        json={"decision": "approved"},
    )
    assert decision.status_code == 200

    async def skip_network_validation(url: str) -> None:
        return None

    monkeypatch.setattr("app.api.routes._validate_source_root", skip_network_validation)
    promoted = await client.post(
        f"/v1/discovery/candidates/{candidate.id}/promote"
    )
    assert promoted.status_code == 201
    body = promoted.json()
    assert body["created"] is True
    assert body["source"]["enabled"] is False
    assert body["source"]["approval_status"] == "approved"
    assert body["source"]["legal_review_status"] == "pending"

    promoted_source = await session.get(Source, body["source_id"])
    assert promoted_source is not None
    assert promoted_source.root_url == "https://example.com/programmes/one"
    assert candidate.promoted_source_id == promoted_source.id

    repeat = await client.post(f"/v1/discovery/candidates/{candidate.id}/promote")
    assert repeat.status_code == 201
    assert repeat.json()["created"] is False


@pytest.mark.integration
async def test_changedetection_webhook_authentication_and_dedup(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(
        webhooks,
        "get_settings",
        lambda: SimpleNamespace(changedetection_webhook_secret="webhook-secret"),
    )
    source = await make_source(
        session,
        name="Watched programme",
        kind=SourceKind.changedetection,
        url="https://example.com/watch",
        config={"watch_uuid": "watch-123"},
    )
    await session.commit()
    payload = json.dumps(
        {
            "watch_uuid": "watch-123",
            "watch_url": "https://example.com/watch",
            "title": "Programme changed",
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"webhook-secret", payload, hashlib.sha256).hexdigest()

    invalid = await client.post(
        "/v1/integrations/changedetection/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-changedetection-signature": "wrong",
        },
    )
    assert invalid.status_code == 401

    accepted = await client.post(
        "/v1/integrations/changedetection/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-changedetection-signature": f"sha256={signature}",
        },
    )
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    job = await session.scalar(select(Job).where(Job.source_id == source.id))
    assert job is not None
    assert job.kind == JobKind.ingest_source

    duplicate = await client.post(
        "/v1/integrations/changedetection/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-changedetection-signature": signature,
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "duplicate"
    event_count = await session.scalar(select(func.count()).select_from(WebhookEvent))
    assert event_count == 1
    job_count = await session.scalar(select(func.count()).select_from(Job))
    assert job_count == 1

    unknown_payload = json.dumps({"watch_uuid": "unknown"}).encode()
    unknown_signature = hmac.new(
        b"webhook-secret", unknown_payload, hashlib.sha256
    ).hexdigest()
    unknown = await client.post(
        "/v1/integrations/changedetection/webhook",
        content=unknown_payload,
        headers={"x-changedetection-signature": unknown_signature},
    )
    assert unknown.status_code == 202
    assert unknown.json()["status"] == "ignored"
    ignored = await session.scalar(
        select(WebhookEvent).where(WebhookEvent.status == "ignored")
    )
    assert ignored is not None
    assert ignored.source_id is None


@pytest.mark.integration
async def test_changedetection_webhook_requires_configuration(
    client: httpx.AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        webhooks,
        "get_settings",
        lambda: SimpleNamespace(changedetection_webhook_secret=None),
    )
    response = await client.post(
        "/v1/integrations/changedetection/webhook",
        json={"watch_uuid": "watch-123"},
    )
    assert response.status_code == 503
