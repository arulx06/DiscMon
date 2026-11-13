from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.http import HttpResponse, SafeFetcher
from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import (
    ApprovalStatus,
    DeadlinePrecision,
    EligibilityStatus,
    HardGateStatus,
    LegalReviewStatus,
    OpportunityType,
    RecommendationBucket,
    SourceKind,
    SyncStatus,
)
from app.db.models.evidence import RawEvidence
from app.db.models.opportunity import Opportunity, OpportunityRevision, OpportunitySource
from app.db.models.source import Source, SourceRun
from app.db.models.sync import SyncOutbox, SyncState
from app.services import discovery, ingestion, sheets
from tests.factories import make_source
from tests.test_discovery_webhook import client  # noqa: F401
from tests.test_sheets import _canonical_snapshot, _mock_gateway


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
    settings = SimpleNamespace(
        sheets_sync_enabled=True, sheets_configured=True,
        google_sheets_spreadsheet_id="synthetic-sheet", google_sheets_tab="Opportunities",
    )
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)
    expected_header = [
        "Opportunity ID", "Title", "Organization", "Type", "Decision", "Bucket", "Score",
        "Professional Eligibility", "India Eligibility", "Location", "Workplace", "Deadline",
        "Deadline Precision", "Official URL", "Next Action", "Follow-up Due", "Last Seen",
    ]
    remote_rows: list[list[str]] = []
    appended_values: list[str] = []

    async def sheets_endpoint(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.url.host == "sheets.googleapis.com"
        assert request.headers["Authorization"] == "Bearer dummy-sheets-token"
        base = "/v4/spreadsheets/synthetic-sheet/values/"
        if request.method == "GET":
            assert request.url.path == base + "'Opportunities'"
            assert dict(request.url.params) == {"majorDimension": "ROWS"}
            assert request.content == b""
            return httpx.Response(200, json={
                "range": "'Opportunities'!A1:Q2", "majorDimension": "ROWS",
                "values": deepcopy(remote_rows),
            })
        payload = json.loads(request.content)
        assert set(payload) == {"values"}
        if request.method == "PUT":
            assert dict(request.url.params) == {"valueInputOption": "RAW"}
            if request.url.path == base + "Opportunities!A1:Q1":
                assert remote_rows == []
                assert payload == {"values": [expected_header]}
                remote_rows.append(payload["values"][0])
                updated_range = "Opportunities!A1:Q1"
            else:
                assert request.url.path == base + "Opportunities!A2:Q2"
                assert len(remote_rows) == 2
                assert payload == {"values": [appended_values]}
                remote_rows[1] = payload["values"][0]
                updated_range = "Opportunities!A2:Q2"
            return httpx.Response(200, json={
                "spreadsheetId": "synthetic-sheet", "updatedRange": updated_range,
                "updatedRows": 1, "updatedColumns": 17, "updatedCells": 17,
            })
        assert request.method == "POST"
        assert request.url.path == base + "Opportunities!A:Q:append"
        assert dict(request.url.params) == {
            "valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS",
        }
        assert len(remote_rows) == 1
        values = payload["values"]
        assert len(values) == 1 and len(values[0]) == 17
        assert all(isinstance(cell, str) for cell in values[0])
        appended_values.extend(values[0])
        remote_rows.append(values[0])
        # The write lands, but its acknowledgement fails at the HTTP boundary.
        return httpx.Response(503, json={"error": {
            "code": 503, "status": "UNAVAILABLE",
            "message": "private-google-detail dummy-sheets-token",
        }})

    gateway, requests, gateways = _mock_gateway(monkeypatch, settings, sheets_endpoint)
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
    assert assessment.opportunity_id == opportunity.id
    assert assessment.revision_id == opportunity.current_revision_id
    assert assessment.hard_gate_status == HardGateStatus.needs_verification
    assert assessment.recommended_bucket == RecommendationBucket.needs_verification
    assert opportunity.deadline_precision == DeadlinePrecision.unknown
    assert opportunity.deadline_on is opportunity.deadline_at is None
    assert opportunity.deadline_timezone is None
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
    assert evidence.content_hash == hashlib.sha256(json.dumps(
        evidence.content_json, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    assert assessment.is_ai_assisted is False
    assert assessment.evidence_refs_json == [{
        "url": programme_url, "observed_at": evidence.fetched_at.isoformat(),
        "excerpt": evidence.extracted_text_excerpt, "source_id": str(promoted_source.id),
        "content_hash": evidence.content_hash,
    }]
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

    assert await session.scalar(select(func.count()).select_from(Alert)) == 0
    canonical_models = (
        Opportunity, OpportunityRevision, OpportunitySource, RawEvidence, Assessment,
    )
    before_sync = {
        model: await _canonical_snapshot(session, model) for model in canonical_models
    }
    opportunity_id = opportunity.id
    failed = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert failed == {
        "enabled": True, "configured": True, "synced": 0, "failed": 1, "skipped": 0,
    }
    assert outbox.status == SyncStatus.failed
    assert outbox.retries == 1
    assert outbox.last_attempt_at is not None
    assert outbox.last_error == "Google Sheets sync failed (HTTP 503)"
    state = (await session.scalars(select(SyncState))).one()
    assert state.last_error == outbox.last_error
    assert state.last_success_at is None
    assert state.remote_row_key is None
    assert gateway.client.is_closed
    assert remote_rows == [expected_header, appended_values]
    failed_attempt_at = outbox.last_attempt_at
    # Reload committed records rather than trusting the session identity map.
    session.expunge_all()
    for model in canonical_models:
        assert await _canonical_snapshot(session, model) == before_sync[model]

    retried = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert retried == {
        "enabled": True, "configured": True, "synced": 1, "failed": 0, "skipped": 0,
    }
    synced = (await session.scalars(select(SyncOutbox))).one()
    assert synced.status == SyncStatus.synced
    assert synced.retries == 1
    assert synced.last_error is None
    assert synced.last_attempt_at >= failed_attempt_at
    state = (await session.scalars(select(SyncState))).one()
    assert state.sheet_id == "synthetic-sheet"
    assert state.tab == "Opportunities"
    assert state.remote_row_key == "2"
    assert state.last_success_at is not None
    assert state.last_error is None
    assert all(item.client.is_closed for item in gateways)

    # Independent read-back uses the real gateway and a fresh transport client.
    async with httpx.AsyncClient(transport=httpx.MockTransport(sheets_endpoint)) as reader:
        readback = await sheets.SheetsGateway(settings, "dummy-sheets-token", reader).rows()
    assert readback == [expected_header, appended_values]
    values = readback[1]
    assert len(readback[0]) == len(values) == 17
    assert [row[0] for row in readback[1:]] == [str(opportunity_id)]
    assert values[1] == "Synthetic Research Fellowship"
    assert values[3] == "fellowship"
    assert values[5] == "needs_verification"
    assert values[7:9] == ["unknown", "unknown"]
    assert values[11:14] == ["", "unknown", programme_url]
    assert [request.method for request in requests] == ["GET", "PUT", "POST", "GET", "PUT"]
    request_count = len(requests)
    again = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert again["synced"] == again["failed"] == again["skipped"] == 0
    assert len(requests) == request_count
    assert len(gateways) == 2
    session.expunge_all()
    for model in canonical_models:
        assert await _canonical_snapshot(session, model) == before_sync[model]
    assert await session.scalar(select(func.count()).select_from(Opportunity)) == 1
    assert await session.scalar(select(func.count()).select_from(OpportunityRevision)) == 1
    assert await session.scalar(select(func.count()).select_from(SyncOutbox)) == 1
    assert await session.scalar(select(func.count()).select_from(Alert)) == 0
