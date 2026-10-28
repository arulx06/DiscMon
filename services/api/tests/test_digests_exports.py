from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent
from app.db.models.digest import Digest
from app.db.models.enums import DeadlinePrecision, DigestKind
from app.db.models.opportunity import Opportunity
from app.db.session import get_db
from app.main import app as fastapi_app
from app.services import ingestion
from app.services.digests import digest_window
from app.services.time import now_utc
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


async def _seed_opportunities(session: AsyncSession, monkeypatch) -> dict[str, Opportunity]:
    now = now_utc()
    candidates = [
        make_candidate(
            external_id="exact",
            title="=CMD() exact deadline role",
            deadline_on=(now + timedelta(days=5)).date(),
            deadline_at=now + timedelta(days=5),
            deadline_precision=DeadlinePrecision.exact,
            deadline_timezone="UTC",
        ),
        make_candidate(
            external_id="date-only",
            title="Date-only deadline role",
            deadline_on=(now + timedelta(days=10)).date(),
            deadline_precision=DeadlinePrecision.date_only,
        ),
        make_candidate(
            external_id="month-only",
            title="Month-only deadline role",
            deadline_on=(now.date().replace(day=1) + timedelta(days=32)).replace(day=1),
            deadline_precision=DeadlinePrecision.month_only,
        ),
    ]
    source = await make_source(session)
    adapter = FakeAdapter(candidates)
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 3
    opportunities = (await session.scalars(select(Opportunity))).all()
    return {opportunity.title: opportunity for opportunity in opportunities}


@pytest.mark.integration
async def test_deadlines_and_calendar_do_not_invent_times(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    seeded = await _seed_opportunities(session, monkeypatch)
    date_only = seeded["Date-only deadline role"]
    exact = seeded["=CMD() exact deadline role"]
    month_only = seeded["Month-only deadline role"]

    deadlines = await client.get("/v1/deadlines")
    assert deadlines.status_code == 200
    body = deadlines.json()
    assert body["total"] == 3
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[str(date_only.id)]["deadline_precision"] == "date_only"
    assert "time not published" in by_id[str(date_only.id)]["deadline_label"]
    assert "month only" in by_id[str(month_only.id)]["deadline_label"]
    assert by_id[str(exact.id)]["days_until_deadline"] == 5

    calendar = await client.get("/v1/deadlines.ics")
    assert calendar.status_code == 200
    assert calendar.headers["content-type"].startswith("text/calendar")
    ics = calendar.text
    assert ics.count("BEGIN:VEVENT") == 2
    assert f"DTSTART;VALUE=DATE:{date_only.deadline_on:%Y%m%d}" in ics
    assert "DTSTART;VALUE=DATE:" in ics
    assert "cutoff time not published" in ics
    assert "Month-only deadline role" not in ics
    assert "exact deadline role" in ics
    year_month = month_only.deadline_on.strftime("%Y%m%d")
    assert year_month not in ics


@pytest.mark.integration
async def test_csv_brief_digest_flow_is_idempotent_and_audited(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    seeded = await _seed_opportunities(session, monkeypatch)
    opportunity = seeded["=CMD() exact deadline role"]

    csv_response = await client.get("/v1/export/opportunities.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    rows = csv_response.text.splitlines()
    assert rows[0].startswith("id,title,organization")
    assert len(rows) == 4
    assert "'=CMD()" in csv_response.text

    opportunity_brief = await client.get(f"/v1/opportunities/{opportunity.id}/brief")
    assert opportunity_brief.status_code == 200
    assert "untrusted source data" in opportunity_brief.json()["markdown"]

    first = await client.post("/v1/digests/generate", params={"kind": "daily"})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["created"] is True
    assert first_body["kind"] == "daily"
    assert len(first_body["opportunity_ids"]) == 3

    second = await client.post("/v1/digests/generate", params={"kind": "daily"})
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == first_body["id"]

    listing = await client.get("/v1/digests", params={"kind": "daily"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["opportunity_count"] == 3

    detail = await client.get(f"/v1/digests/{first_body['id']}")
    assert detail.status_code == 200
    assert "# DiscMon Daily Brief" in detail.json()["content_md"]
    assert "Unknown is not yes." in detail.json()["content_md"]
    assert detail.json()["content_json"]["kind"] == "daily"

    reviewed = await client.post(f"/v1/digests/{first_body['id']}/reviewed")
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed_at"] is not None
    detail_after = await client.get(f"/v1/digests/{first_body['id']}")
    assert detail_after.json()["sent_status"] == "reviewed"

    weekly = await client.get("/v1/export/brief.md")
    assert weekly.status_code == 200
    assert "# DiscMon Weekly Brief" in weekly.text
    assert "Unknown is not yes." in weekly.text

    audit_types = (
        await session.execute(
            select(AuditEvent.event_type, func.count(AuditEvent.id)).group_by(AuditEvent.event_type)
        )
    ).all()
    counts = {event_type: count for event_type, count in audit_types}
    assert counts["data.export"] == 2
    assert counts["digest.generated"] == 1
    assert counts["digest.reviewed"] == 1


@pytest.mark.integration
async def test_digest_excludes_fixtures_and_ignores_demo_window(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    seeded = await _seed_opportunities(session, monkeypatch)
    fixture = seeded["Month-only deadline role"]
    fixture.is_fixture = True
    start, end = digest_window(DigestKind.daily)
    demo = Digest(
        period_start=start,
        period_end=end,
        digest_kind=DigestKind.daily,
        content_md="# [Demo] Daily digest",
        content_json={"demo": True},
        opportunity_ids=[str(fixture.id)],
        sent_status="demo",
    )
    session.add(demo)
    await session.commit()

    response = await client.post("/v1/digests/generate", params={"kind": "daily"})
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert str(fixture.id) not in body["opportunity_ids"]
    assert len(body["opportunity_ids"]) == 2

    detail = await client.get(f"/v1/digests/{body['id']}")
    assert detail.status_code == 200
    assert "[Demo]" not in detail.json()["content_md"]
