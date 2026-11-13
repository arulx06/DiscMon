from __future__ import annotations

import hashlib
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.http import HttpResponse, SafeFetcher
from app.db.models.assessment import Assessment
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import (
    ApprovalStatus,
    EligibilityStatus,
    LegalReviewStatus,
    OpportunityType,
    SourceKind,
    SyncStatus,
)
from app.db.models.evidence import RawEvidence
from app.db.models.opportunity import Opportunity, OpportunityRevision, OpportunitySource
from app.db.models.source import Source, SourceRun
from app.db.models.sync import SyncOutbox
from app.services import discovery, ingestion, sheets
from tests.factories import make_source
from tests.test_discovery_webhook import client  # noqa: F401
from tests.test_sheets import FakeSheetsGateway


@pytest.mark.integration
async def test_discovery_to_sheets_preserves_gates_and_canonical_records(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch  # noqa: F811
) -> None:
    programme_url = "https://example.com/programmes/synthetic-fellowship"
    programme_html = b"""
    <main><h1>Synthetic Research Fellowship</h1>
    <p>A remote fellowship for research collaboration.</p></main>
    """
    pages = {
        "https://example.com/programmes": (
            b'<a href="/programmes/synthetic-fellowship">Synthetic fellowship</a>'
        ),
        programme_url: programme_html,
    }
    fetched: list[str] = []

    async def fixture_get(self, url, **kwargs):
        fetched.append(url)
        return HttpResponse(
            url=url, status_code=200, headers={"content-type": "text/html"},
            content=pages[url], elapsed_ms=0,
        )

    async def validate_fixture_url(url: str) -> None:
        assert url in pages

    monkeypatch.setattr(SafeFetcher, "get", fixture_get)
    monkeypatch.setattr("app.api.routes._validate_source_root", validate_fixture_url)
    monkeypatch.setattr(sheets, "get_settings", lambda: SimpleNamespace(
        sheets_sync_enabled=True, sheets_configured=True,
        google_sheets_spreadsheet_id="synthetic-sheet", google_sheets_tab="Opportunities",
    ))
    monkeypatch.setattr(FakeSheetsGateway, "instances", [])
    gateway = FakeSheetsGateway()

    async def create_gateway(cls, settings):
        gateway.closed = False
        return gateway

    monkeypatch.setattr(FakeSheetsGateway, "create", classmethod(create_gateway))
    monkeypatch.setattr(sheets, "SheetsGateway", FakeSheetsGateway)
    source = await make_source(
        session, name="Synthetic programme directory", kind=SourceKind.static_html,
        url="https://example.com/programmes",
        config={"discovery": {"enabled": True, "allowed_domains": ["example.com"]}},
    )
    await session.commit()
    found = await discovery.run_discovery(session, source.id)
    await session.commit()
    assert found.created == 1
    candidate = (await session.scalars(select(DiscoveryCandidate))).one()
    assert candidate.found_via_source_id == source.id
    assert candidate.candidate_url == programme_url
    assert candidate.suggested_adapter == SourceKind.static_html
    assert candidate.approval_status == ApprovalStatus.candidate
    review = await client.get("/v1/discovery/candidates")
    assert review.status_code == 200
    assert review.json()["items"][0]["id"] == str(candidate.id)
    promote_url = f"/v1/discovery/candidates/{candidate.id}/promote"
    assert (await client.post(promote_url)).status_code == 400
    decision = await client.post(
        f"/v1/discovery/candidates/{candidate.id}/decision", json={"decision": "approved"},
    )
    assert decision.status_code == 200
    promoted = await client.post(promote_url)
    assert promoted.status_code == 201
    assert promoted.json()["created"] is True
    promoted_source = await session.get(Source, candidate.promoted_source_id)
    assert promoted_source is not None
    assert promoted_source.enabled is False
    assert promoted_source.approval_status == ApprovalStatus.approved
    assert promoted_source.legal_review_status == LegalReviewStatus.pending
    repeat = await client.post(promote_url)
    assert repeat.status_code == 201
    assert repeat.json()["created"] is False
    assert repeat.json()["source_id"] == str(promoted_source.id)
    assert await session.scalar(select(func.count()).select_from(Source)) == 2

    with pytest.raises(ValueError, match="disabled"):
        await ingestion.ingest_source(session, promoted_source.id)
    enable = await client.patch(
        f"/v1/sources/{promoted_source.id}", json={"enabled": True},
    )
    assert enable.status_code == 400
    # Inconsistent enabled rows must not bypass service-level approval gates.
    promoted_source.enabled = True
    for approval, legal in (
        (ApprovalStatus.candidate, LegalReviewStatus.approved),
        (ApprovalStatus.approved, LegalReviewStatus.pending),
    ):
        promoted_source.approval_status = approval
        promoted_source.legal_review_status = legal
        with pytest.raises(ValueError, match="approval and legal review"):
            await ingestion.ingest_source(session, promoted_source.id)
    assert fetched == [source.root_url]
    assert await session.scalar(select(func.count()).select_from(SourceRun)) == 0
    assert await session.scalar(select(func.count()).select_from(Opportunity)) == 0
    promoted_source.enabled = False
    await session.commit()

    approved = await client.patch(f"/v1/sources/{promoted_source.id}", json={
        "approval_status": "approved", "legal_review_status": "approved", "enabled": True,
        "config_json": {"remote": True, "organization_name": "Synthetic Programme"},
    })
    assert approved.status_code == 200
    first = await ingestion.ingest_source(session, promoted_source.id)
    await session.commit()
    assert first.created == 1
    opportunity = (await session.scalars(select(Opportunity))).one()
    assert opportunity.title == "Synthetic Research Fellowship"
    assert opportunity.opportunity_type == OpportunityType.fellowship
    assert opportunity.india_eligibility == EligibilityStatus.unknown
    assessment = (await session.scalars(select(Assessment))).one()
    assert assessment.professional_eligibility_state == EligibilityStatus.unknown
    assert assessment.india_eligibility_state == EligibilityStatus.unknown
    link = (await session.scalars(select(OpportunitySource))).one()
    assert link.opportunity_id == opportunity.id
    assert link.source_id == promoted_source.id
    assert link.source_item_url == programme_url
    evidence = await session.get(RawEvidence, link.raw_evidence_id)
    assert evidence is not None
    assert evidence.source_id == promoted_source.id
    assert evidence.source_url == programme_url
    assert evidence.content_json["source_payload"]["page_hash"] == (
        hashlib.sha256(programme_html).hexdigest()
    )
    assert evidence.content_json["is_remote"] is True
    assert "remote fellowship" in evidence.extracted_text_excerpt
    revision = await session.get(OpportunityRevision, opportunity.current_revision_id)
    assert revision is not None
    assert str(evidence.id) in revision.evidence_ids
    second = await ingestion.ingest_source(session, promoted_source.id)
    await session.commit()
    assert second.created == second.updated == 0
    assert await session.scalar(select(func.count()).select_from(Opportunity)) == 1
    assert await session.scalar(select(func.count()).select_from(OpportunityRevision)) == 1
    outbox = (await session.scalars(select(SyncOutbox))).one()
    assert outbox.entity_id == opportunity.id
    assert outbox.status == SyncStatus.pending

    original_append = gateway.append_row

    async def append_then_fail(values):
        row_number = await original_append(values)
        gateway.rows_data = [sheets.SHEET_HEADERS, values]
        assert row_number == 2
        # Model a remote write followed by a lost acknowledgement.
        raise RuntimeError("synthetic Sheets acknowledgement failure")

    monkeypatch.setattr(gateway, "append_row", append_then_fail)
    failed = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert failed["failed"] == 1
    assert outbox.status == SyncStatus.failed
    assert outbox.retries == 1
    assert outbox.last_error == "Google Sheets sync failed"
    assert gateway.closed is True
    # Reload committed records, not merely objects retained in the session identity map.
    opportunity_id, revision_id, evidence_id = opportunity.id, revision.id, evidence.id
    session.expunge_all()
    assert await session.get(Opportunity, opportunity_id) is not None
    assert await session.get(OpportunityRevision, revision_id) is not None
    assert await session.get(RawEvidence, evidence_id) is not None
    monkeypatch.setattr(gateway, "append_row", original_append)
    retried = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert retried["synced"] == 1
    synced = (await session.scalars(select(SyncOutbox))).one()
    assert synced.status == SyncStatus.synced
    assert synced.last_error is None
    assert len(gateway.appended) == 1
    assert len(gateway.updated) == 1
    row_number, values = gateway.updated[0]
    assert row_number == 2
    assert values[0] == str(opportunity_id)
    assert values[1] == "Synthetic Research Fellowship"
    assert values[sheets.SHEET_HEADERS.index("Official URL")] == programme_url
    assert gateway.closed is True
    again = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert again["synced"] == 0
    assert len(gateway.appended) == len(gateway.updated) == 1
    assert await session.scalar(select(func.count()).select_from(Opportunity)) == 1
