from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.enums import LifeState, RevisionType
from app.db.models.evidence import RawEvidence
from app.db.models.opportunity import Opportunity, OpportunityRevision, OpportunitySource
from app.db.models.source import SourceRun
from app.schemas.collector import CompensationDTO
from app.services import ingestion
from tests.factories import FakeAdapter, make_candidate, make_source


@pytest.mark.integration
async def test_ingestion_is_idempotent_and_dedups_alerts(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    first = await ingestion.ingest_source(session, source.id)
    await session.commit()
    second = await ingestion.ingest_source(session, source.id)
    await session.commit()

    assert first.status == "success"
    assert first.created == 1
    assert second.status == "success"
    assert second.created == 0
    assert second.skipped == 1
    opportunity_count = await session.scalar(select(func.count(Opportunity.id)))
    revision_count = await session.scalar(select(func.count(OpportunityRevision.id)))
    link_count = await session.scalar(select(func.count(OpportunitySource.opportunity_id)))
    evidence_count = await session.scalar(select(func.count(RawEvidence.id)))
    alert_count = await session.scalar(select(func.count(Alert.id)))
    run_count = await session.scalar(select(func.count(SourceRun.id)))
    assert opportunity_count == 1
    assert revision_count == 1
    assert link_count == 1
    assert evidence_count == 2
    assert alert_count == 1
    assert run_count == 2
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    assert opportunity.provider_key == "fake:1"
    assert opportunity.life_state in {LifeState.open, LifeState.upcoming}
    assert opportunity.india_eligibility.value == "verified_yes"
    assert opportunity.professional_eligibility.value == "verified_yes"


@pytest.mark.integration
async def test_volatile_compensation_ids_do_not_create_revisions(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    candidate = make_candidate()
    candidate.compensation = CompensationDTO(
        raw="{'tiers': [{'id': 'first-id', 'summary': 'USD 120K'}]}",
        summary="USD 120K",
        cash="USD 120K",
        currency="USD",
        period="per year",
    )
    adapter = FakeAdapter([candidate])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    candidate.compensation.raw = "{'tiers': [{'id': 'second-id', 'summary': 'USD 120K'}]}"
    second = await ingestion.ingest_source(session, source.id)
    await session.commit()

    assert second.updated == 0
    assert second.skipped == 1
    assert await session.scalar(select(func.count(OpportunityRevision.id))) == 1


@pytest.mark.integration
async def test_material_change_creates_one_revision_and_one_alert(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    adapter.candidates = [make_candidate(title="Staff Backend Engineer")]
    changed = await ingestion.ingest_source(session, source.id)
    await session.commit()
    unchanged = await ingestion.ingest_source(session, source.id)
    await session.commit()

    assert changed.updated == 1
    assert unchanged.updated == 0
    revisions = (
        (
            await session.execute(
                select(OpportunityRevision).order_by(OpportunityRevision.revision_number)
            )
        )
        .scalars()
        .all()
    )
    assert [revision.revision_number for revision in revisions] == [1, 2]
    assert revisions[1].revision_type == RevisionType.updated
    assert revisions[1].material_diff_json["title"]["new"] == "Staff Backend Engineer"
    assert await session.scalar(select(func.count(Alert.id))) == 2
    keys = (await session.execute(select(Alert.dedup_key))).scalars().all()
    assert len(keys) == len(set(keys))


@pytest.mark.integration
async def test_failed_scan_is_visible_and_never_closes_records(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    adapter.mode = "raise"
    failed = await ingestion.ingest_source(session, source.id)
    await session.commit()

    assert failed.status == "failed"
    failed_run = await session.get(SourceRun, failed.run_id)
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_category == "RuntimeError"
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    assert opportunity.life_state == LifeState.open
    link = await session.scalar(select(OpportunitySource))
    assert link is not None
    assert link.absence_count == 0
    refreshed_source = await session.get(type(source), source.id)
    assert refreshed_source is not None
    assert refreshed_source.consecutive_failures == 1
    assert refreshed_source.health_status.value == "stale"
    assert refreshed_source.last_error_redacted is not None


@pytest.mark.integration
async def test_partial_scan_never_increments_absence(session: AsyncSession, monkeypatch) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    adapter.candidates = []
    adapter.scan_complete = False
    partial = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert partial.scan_complete is False
    link = await session.scalar(select(OpportunitySource))
    assert link is not None
    assert link.absence_count == 0


@pytest.mark.integration
async def test_three_complete_absences_then_confirmation_close_opportunity(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    adapter.candidates = []
    for _ in range(2):
        await ingestion.ingest_source(session, source.id)
        await session.commit()
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    assert opportunity.life_state == LifeState.open

    third_absence = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert third_absence.updated == 0
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    assert opportunity.life_state == LifeState.closed
    latest_type = await session.scalar(
        select(OpportunityRevision.revision_type)
        .where(OpportunityRevision.opportunity_id == opportunity.id)
        .order_by(OpportunityRevision.revision_number.desc())
        .limit(1)
    )
    assert latest_type == RevisionType.closed_candidate

    fourth_absence = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert fourth_absence.status == "success"
    latest_type = await session.scalar(
        select(OpportunityRevision.revision_type)
        .where(OpportunityRevision.opportunity_id == opportunity.id)
        .order_by(OpportunityRevision.revision_number.desc())
        .limit(1)
    )
    assert latest_type == RevisionType.closed_confirmed


@pytest.mark.integration
async def test_parse_error_is_recorded_without_erasing_existing_records(
    session: AsyncSession, monkeypatch
) -> None:
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()

    await ingestion.ingest_source(session, source.id)
    await session.commit()
    adapter.mode = "parse_error"
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.status == "failed"
    assert await session.scalar(select(func.count(Opportunity.id))) == 1
    assert await session.scalar(select(func.count(Assessment.id))) == 1


@pytest.mark.integration
@pytest.mark.parametrize("missing_url", [None, "", "javascript:void(0)"])
async def test_application_evidence_survives_missing_or_invalid_update(
    session: AsyncSession, monkeypatch, missing_url: str | None
) -> None:
    source = await make_source(session)
    candidate = make_candidate()
    adapter = FakeAdapter([candidate])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    assert (await ingestion.ingest_source(session, source.id)).created == 1
    await session.commit()
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity is not None
    verified_url = candidate.application_url
    assert opportunity.application_url == verified_url

    candidate.application_url = missing_url
    assert (await ingestion.ingest_source(session, source.id)).skipped == 1
    await session.commit()
    await session.refresh(opportunity)
    assert opportunity.application_url == verified_url

    candidate.application_url = "https://example.com/verified-new-application"
    assert (await ingestion.ingest_source(session, source.id)).updated == 1
    await session.commit()
    await session.refresh(opportunity)
    assert opportunity.application_url == candidate.application_url
