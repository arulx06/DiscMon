from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent
from app.db.models.opportunity import Opportunity
from app.db.session import get_db
from app.main import app as fastapi_app
from app.services import ingestion
from tests.factories import FakeAdapter, make_candidate, make_source


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    async def override_get_db():
        yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    fastapi_app.dependency_overrides.clear()


async def _seed_opportunity(session: AsyncSession, monkeypatch) -> Opportunity:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 1
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    return opportunity


@pytest.mark.integration
async def test_api_read_and_review_flow(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    opportunity = await _seed_opportunity(session, monkeypatch)

    health = await client.get("/health/live")
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

    integrations = await client.get("/v1/integrations/status")
    assert integrations.status_code == 200
    assert integrations.json()["sheets"]["tab"] == "Opportunities"
    assert integrations.json()["ai"]["enabled"] is False

    dashboard = await client.get("/v1/dashboard")
    assert dashboard.status_code == 200
    dashboard_body = dashboard.json()
    assert dashboard_body["active_opportunities"] == 1
    assert dashboard_body["pending_alerts"] >= 1
    assert dashboard_body["scan_is_partial"] is False

    listing = await client.get("/v1/opportunities")
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["total"] == 1
    card = listing_body["items"][0]
    assert card["id"] == str(opportunity.id)
    assert card["professional_eligibility"] == "verified_yes"
    assert card["india_eligibility"] == "verified_yes"

    detail = await client.get(f"/v1/opportunities/{opportunity.id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["application_url"] == opportunity.application_url
    assert len(detail_body["revisions"]) == 1
    assert detail_body["revisions"][0]["type"] == "created"
    assert detail_body["sources"][0]["absence_count"] == 0
    assert detail_body["assessment"]["score"] is not None

    review = await client.post(
        f"/v1/opportunities/{opportunity.id}/review",
        json={
            "decision": "apply",
            "note": "Prepare application",
            "next_action": "Draft application answers",
            "followup_due_at": "2030-01-15T09:00:00Z",
        },
    )
    assert review.status_code == 200
    assert review.json()["decision"] == "apply"

    refreshed = await client.get(f"/v1/opportunities/{opportunity.id}")
    assert refreshed.json()["user_decision"] == "apply"
    assert refreshed.json()["notes"] == "Prepare application"
    assert refreshed.json()["next_action"] == "Draft application answers"
    assert refreshed.json()["followup_due_at"] == "2030-01-15T09:00:00+00:00"

    watchlist = await client.get("/v1/watchlist")
    assert watchlist.status_code == 200
    apply_group = next(
        group for group in watchlist.json()["groups"] if group["key"] == "apply"
    )
    assert apply_group["total"] == 1
    assert apply_group["items"][0]["next_action"] == "Draft application answers"
    assert apply_group["items"][0]["followup_due_at"] == "2030-01-15T09:00:00+00:00"
    assert watchlist.json()["followups_due"] == 0
    audit_event = await session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "opportunity.review")
    )
    assert audit_event is not None

    sources = await client.get("/v1/sources")
    assert sources.status_code == 200
    source_item = sources.json()["items"][0]
    assert source_item["last_run"]["status"] == "success"
    assert source_item["consecutive_failures"] == 0

    alerts = await client.get("/v1/alerts")
    assert alerts.status_code == 200
    assert alerts.json()["items"][0]["status"] == "pending"
    assert alerts.json()["items"][0]["payload"]["india_eligibility"] == "verified_yes"

    jobs = await client.get("/v1/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["active"] == {}

    system = await client.get("/v1/system/status")
    assert system.status_code == 200
    assert system.json()["database"] == "ok"


@pytest.mark.integration
async def test_api_missing_opportunity_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/v1/opportunities/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
