from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import get_adapter
from app.collectors.http import FetchPolicy, SafeFetcher
from app.db.models.enums import (
    CredibilityLevel,
    HealthStatus,
    LifeState,
    RevisionType,
)
from app.db.models.evidence import RawEvidence
from app.db.models.opportunity import (
    Opportunity,
    OpportunityRevision,
    OpportunitySource,
    Organization,
)
from app.db.models.source import Source, SourceRun
from app.schemas.collector import NormalizedCandidate, SourceConfig
from app.services.alerts import maybe_create_alerts
from app.services.assessment import assess_opportunity, get_or_create_profile
from app.services.eligibility import assess_eligibility
from app.services.revisions import (
    diff_snapshots,
    material_snapshot,
    snapshot_hash,
)
from app.services.sheets import enqueue_sheet_upsert
from app.services.time import deadline_state, ensure_utc, now_utc
from app.services.urls import canonicalize_url, is_http_url


@dataclass
class IngestOutcome:
    source_id: uuid.UUID
    run_id: uuid.UUID
    status: str
    records_seen: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    scan_complete: bool = False
    error_category: str | None = None
    error_message: str | None = None
    revisions: list[uuid.UUID] = field(default_factory=list)


def _credibility(source: Source) -> CredibilityLevel:
    return {
        "official": CredibilityLevel.high,
        "credible_aggregator": CredibilityLevel.medium,
        "unknown": CredibilityLevel.unknown,
    }.get(source.officialness.value, CredibilityLevel.unknown)


def _next_due(source: Source, now: datetime) -> datetime:
    hours = float(source.interval_hours or Decimal("24"))
    return now + timedelta(hours=max(1.0, hours))


def _safe_error(exc: BaseException) -> tuple[str, str]:
    category = type(exc).__name__
    message = str(exc).replace("\n", " ")[:400]
    if "://" in message:
        message = "Source operation failed; URL and transport details are in server logs only"
    return category, message


async def _upsert_organization(
    session: AsyncSession,
    candidate: NormalizedCandidate,
    source: Source,
) -> Organization:
    organization = None
    if candidate.organization_domain:
        organization = await session.scalar(
            select(Organization).where(
                Organization.canonical_domain == candidate.organization_domain
            )
        )
    if organization is None:
        organization = await session.scalar(
            select(Organization).where(
                func.lower(Organization.canonical_name) == candidate.organization_name.lower()
            )
        )
    if organization is None:
        organization = Organization(
            canonical_name=candidate.organization_name[:300],
            canonical_domain=candidate.organization_domain,
            aliases=[],
            industry_tags=[],
            careers_url=(source.root_url if source.officialness.value == "official" else None),
        )
        session.add(organization)
        await session.flush()
    elif candidate.organization_name != organization.canonical_name:
        if candidate.organization_name not in organization.aliases:
            organization.aliases = [*organization.aliases, candidate.organization_name][:20]
    return organization


def _apply_candidate(
    opportunity: Opportunity,
    candidate: NormalizedCandidate,
    source: Source,
    organization: Organization,
    now: datetime,
) -> None:
    eligibility = assess_eligibility(candidate)
    opportunity.title = candidate.title[:500]
    opportunity.organization_id = organization.id
    opportunity.opportunity_type = candidate.opportunity_type
    if candidate.description_summary is not None:
        opportunity.description_summary = candidate.description_summary
    if candidate.requirements_summary is not None:
        opportunity.requirements_summary = candidate.requirements_summary
    if candidate.scope is not None:
        opportunity.scope = candidate.scope
    if candidate.skills:
        opportunity.skills = sorted({str(skill).lower() for skill in candidate.skills})[:40]
    if candidate.employment_type is not None:
        opportunity.employment_type = candidate.employment_type[:80]
    opportunity.country_codes = sorted(set(candidate.country_codes))
    opportunity.allowed_remote_countries = sorted(set(candidate.allowed_remote_countries))
    if candidate.location_text is not None:
        opportunity.location_text = candidate.location_text[:500]
    if candidate.workplace_type and candidate.workplace_type != "unknown":
        opportunity.workplace_type = candidate.workplace_type
    elif opportunity.workplace_type is None:
        opportunity.workplace_type = "unknown"
    opportunity.requires_relocation = candidate.requires_relocation
    opportunity.employment_conflict = (
        candidate.employment_conflict or opportunity.employment_conflict
    )
    opportunity.official_url = canonicalize_url(candidate.official_url)
    opportunity.application_url = (
        canonicalize_url(candidate.application_url)
        if candidate.application_url and is_http_url(candidate.application_url)
        else opportunity.official_url
    )
    opportunity.opens_on = candidate.opens_on or opportunity.opens_on
    if candidate.deadline_precision.value != "unknown":
        opportunity.deadline_on = candidate.deadline_on
        opportunity.deadline_at = ensure_utc(candidate.deadline_at)
        opportunity.deadline_timezone = candidate.deadline_timezone
        opportunity.deadline_precision = candidate.deadline_precision
    opportunity.compensation_summary = candidate.compensation.summary
    compensation = candidate.compensation.model_dump(exclude_none=True)
    if compensation:
        semantic = {key: value for key, value in compensation.items() if key != "raw"}
        current = opportunity.monetary_value_json or {}
        current_semantic = {key: value for key, value in current.items() if key != "raw"}
        if semantic != current_semantic:
            opportunity.monetary_value_json = compensation
    opportunity.professional_eligibility = eligibility.professional_eligibility
    opportunity.india_eligibility = eligibility.india_eligibility
    opportunity.student_only = eligibility.student_only
    opportunity.student_eligibility = eligibility.student_eligibility
    opportunity.eligibility_reasons_json = eligibility.reasons
    opportunity.eligibility_checked_at = now
    opportunity.credibility_level = _credibility(source)
    if opportunity.provider_key is None and candidate.provider_key:
        opportunity.provider_key = candidate.provider_key[:512]
        opportunity.provider_source_kind = source.source_kind
    opportunity.last_seen_at = now
    opportunity.last_verified_at = now
    state = deadline_state(opportunity.opens_on, opportunity.deadline_on, opportunity.deadline_at)
    opportunity.life_state = LifeState(state)


async def _create_revision(
    session: AsyncSession,
    opportunity: Opportunity,
    organization_name: str,
    revision_type: RevisionType,
    run: SourceRun,
    now: datetime,
    evidence_ids: list[str] | None = None,
    previous_snapshot: dict | None = None,
) -> OpportunityRevision:
    snapshot = material_snapshot(opportunity, organization_name)
    revision = OpportunityRevision(
        opportunity_id=opportunity.id,
        revision_number=opportunity.current_revision_number + 1,
        normalized_snapshot_json=snapshot,
        normalized_hash=snapshot_hash(snapshot),
        material_diff_json=diff_snapshots(previous_snapshot, snapshot),
        observed_at=now,
        source_run_id=run.id,
        evidence_ids=evidence_ids or [],
        revision_type=revision_type,
    )
    session.add(revision)
    await session.flush()
    opportunity.current_revision_id = revision.id
    opportunity.current_revision_number = revision.revision_number
    if revision_type in {RevisionType.updated, RevisionType.reopened, RevisionType.created}:
        opportunity.last_material_change_at = now
    return revision


async def _get_previous_snapshot(
    session: AsyncSession, opportunity: Opportunity
) -> OpportunityRevision | None:
    if opportunity.current_revision_id is None:
        return None
    return await session.get(OpportunityRevision, opportunity.current_revision_id)


async def _upsert_candidate(
    session: AsyncSession,
    source: Source,
    run: SourceRun,
    result,
    candidate: NormalizedCandidate,
    profile,
    now: datetime,
) -> tuple[Opportunity, list[OpportunityRevision]]:
    if not candidate.title.strip():
        raise ValueError("Candidate title is empty")
    if not is_http_url(candidate.official_url):
        raise ValueError("Candidate official_url must be an absolute http(s) URL")
    organization = await _upsert_organization(session, candidate, source)
    opportunity = None
    if candidate.provider_key:
        opportunity = await session.scalar(
            select(Opportunity).where(Opportunity.provider_key == candidate.provider_key)
        )
    canonical_url = canonicalize_url(candidate.official_url)
    if opportunity is None:
        opportunity = await session.scalar(
            select(Opportunity).where(Opportunity.official_url == canonical_url)
        )
    created_now = False
    if opportunity is None:
        opportunity = Opportunity(
            provider_key=(candidate.provider_key[:512] if candidate.provider_key else None),
            provider_source_kind=source.source_kind if candidate.provider_key else None,
            title=candidate.title[:500],
            official_url=canonical_url,
            first_seen_at=now,
            last_seen_at=now,
            life_state=LifeState.open,
            current_revision_number=0,
            is_fixture=candidate.is_fixture,
        )
        session.add(opportunity)
        await session.flush()
        created_now = True

    old_life = opportunity.life_state
    previous_revision = await _get_previous_snapshot(session, opportunity)
    previous_snapshot = previous_revision.normalized_snapshot_json if previous_revision else None
    _apply_candidate(opportunity, candidate, source, organization, now)

    evidence_payload = candidate.model_dump(mode="json")
    evidence_serialized = json.dumps(
        evidence_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    evidence_hash = hashlib.sha256(evidence_serialized.encode("utf-8")).hexdigest()
    evidence = RawEvidence(
        source_id=source.id,
        source_run_id=run.id,
        source_url=result.source_url or source.root_url,
        canonical_url=canonical_url,
        fetched_at=result.fetched_at,
        published_at=ensure_utc(candidate.published_at),
        content_type=result.content_type,
        http_etag=result.etag,
        http_last_modified=result.last_modified,
        content_hash=evidence_hash,
        extracted_text_excerpt=candidate.evidence_excerpt,
        content_json=evidence_payload,
        retention_until=now + timedelta(days=90),
        source_license_or_terms_note=source.config_json.get("license_note"),
    )
    session.add(evidence)
    await session.flush()

    link = await session.get(
        OpportunitySource,
        (opportunity.id, source.id, candidate.source_external_id),
    )
    if link is None:
        link = OpportunitySource(
            opportunity_id=opportunity.id,
            source_id=source.id,
            source_external_id=candidate.source_external_id[:512],
            source_item_url=canonical_url,
            raw_evidence_id=evidence.id,
            first_seen_at=now,
            last_seen_at=now,
            last_seen_run_id=run.id,
            absence_count=0,
        )
        session.add(link)
    else:
        link.last_seen_at = now
        link.last_seen_run_id = run.id
        link.absence_count = 0
        link.raw_evidence_id = evidence.id
        link.source_item_url = canonical_url
    await session.flush()

    revisions: list[OpportunityRevision] = []
    snapshot = material_snapshot(opportunity, organization.canonical_name)
    new_hash = snapshot_hash(snapshot)
    if previous_revision is None:
        revisions.append(
            await _create_revision(
                session,
                opportunity,
                organization.canonical_name,
                RevisionType.reopened if old_life == LifeState.closed else RevisionType.created,
                run,
                now,
                evidence_ids=[str(evidence.id)],
            )
        )
    elif previous_revision.normalized_hash != new_hash:
        revision_type = (
            RevisionType.reopened
            if old_life == LifeState.closed and opportunity.life_state != LifeState.closed
            else RevisionType.updated
        )
        revisions.append(
            await _create_revision(
                session,
                opportunity,
                organization.canonical_name,
                revision_type,
                run,
                now,
                evidence_ids=[str(evidence.id)],
                previous_snapshot=previous_snapshot,
            )
        )
    else:
        if previous_revision is not None:
            evidence_ids = list(previous_revision.evidence_ids or [])
            evidence_ids.append(str(evidence.id))
            previous_revision.evidence_ids = evidence_ids[-20:]
        if opportunity.current_revision_id is None:
            opportunity.current_revision_id = previous_revision.id if previous_revision else None

    assessment, _ = await assess_opportunity(
        session, opportunity, profile, opportunity.current_revision_id
    )
    if revisions and not opportunity.is_fixture:
        await maybe_create_alerts(
            session, opportunity, assessment, revisions[0], profile, organization.canonical_name
        )
    if revisions or created_now:
        await enqueue_sheet_upsert(session, opportunity.id)
    if created_now:
        run.records_created += 1
    elif revisions:
        run.records_updated += 1
    else:
        run.records_skipped += 1
    return opportunity, revisions


async def _apply_absence_closure(
    session: AsyncSession,
    source: Source,
    run: SourceRun,
    now: datetime,
) -> list[OpportunityRevision]:
    links = (
        (
            await session.execute(
                select(OpportunitySource).where(OpportunitySource.source_id == source.id)
            )
        )
        .scalars()
        .all()
    )
    touched_opportunities: set[uuid.UUID] = set()
    for link in links:
        if link.last_seen_run_id != run.id:
            link.absence_count += 1
            touched_opportunities.add(link.opportunity_id)
    await session.flush()

    revisions: list[OpportunityRevision] = []
    for opportunity_id in touched_opportunities:
        opportunity = await session.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.life_state in {
            LifeState.archived,
            LifeState.expired_unverified,
        }:
            continue
        all_links = (
            (
                await session.execute(
                    select(OpportunitySource).where(
                        OpportunitySource.opportunity_id == opportunity_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not all_links or not all(link.absence_count >= 3 for link in all_links):
            continue
        latest_revision_type = (
            await session.execute(
                select(OpportunityRevision.revision_type)
                .where(OpportunityRevision.opportunity_id == opportunity_id)
                .order_by(OpportunityRevision.revision_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_revision_type == RevisionType.closed_confirmed:
            continue
        if latest_revision_type == RevisionType.closed_candidate and not all(
            link.absence_count >= 4 for link in all_links
        ):
            continue
        revision_type = (
            RevisionType.closed_confirmed
            if latest_revision_type == RevisionType.closed_candidate
            else RevisionType.closed_candidate
        )
        organization_name = "Unknown"
        if opportunity.organization_id:
            organization_name = (
                await session.scalar(
                    select(Organization.canonical_name).where(
                        Organization.id == opportunity.organization_id
                    )
                )
            ) or "Unknown"
        opportunity.life_state = LifeState.closed
        revisions.append(
            await _create_revision(
                session,
                opportunity,
                organization_name,
                revision_type,
                run,
                now,
            )
        )
    return revisions


async def _record_failure(
    session: AsyncSession,
    source: Source,
    run: SourceRun,
    category: str,
    message: str,
    now: datetime,
    http_status: int | None = None,
) -> None:
    run.status = "failed"
    run.finished_at = now
    run.error_category = category[:80]
    run.error_message_redacted = message[:1000]
    run.http_status = http_status
    source.last_attempt_at = now
    source.last_error_at = now
    source.last_error_category = category[:80]
    source.last_error_redacted = message[:1000]
    source.consecutive_failures += 1
    source.health_status = (
        HealthStatus.failing if source.consecutive_failures >= 5 else HealthStatus.stale
    )
    source.next_due_at = now + timedelta(hours=min(float(source.interval_hours or 24), 1.0))
    await session.flush()


async def ingest_source(
    session: AsyncSession,
    source_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
) -> IngestOutcome:
    source = await session.get(Source, source_id)
    if source is None:
        raise ValueError(f"Source {source_id} does not exist")
    if not source.enabled:
        raise ValueError(f"Source {source_id} is disabled")
    now = now_utc()
    run = SourceRun(
        source_id=source.id,
        job_id=job_id,
        started_at=now,
        status="running",
        scan_complete=False,
    )
    session.add(run)
    await session.flush()
    profile = await get_or_create_profile(session)
    adapter = get_adapter(source.source_kind.value)
    source_config = SourceConfig(
        id=source.id,
        name=source.name,
        source_kind=source.source_kind,
        root_url=source.root_url,
        config_json=source.config_json or {},
        officialness=source.officialness.value,
        rate_limit_json=source.rate_limit_json or {},
    )
    source.last_attempt_at = now
    fetcher: SafeFetcher | None = None
    try:
        per_minute = int(source.rate_limit_json.get("per_minute", 20))
        policy = FetchPolicy(
            allowed_hosts=adapter.allowed_hosts(source_config),
            min_interval_seconds=(60.0 / per_minute) if per_minute > 0 else 0.0,
        )
        fetcher = SafeFetcher(policy)
        result = await adapter.fetch(source_config, fetcher, cursor=None)
        run.http_status = result.http_status
        run.bytes_received = len(result.raw_bytes)
        run.fetch_duration_ms = 0
        run.snapshot_hash = result.raw_hash
        run.cursor_after = result.cursor
        if result.not_modified:
            run.status = "not_modified"
            run.finished_at = now_utc()
            source.last_success_at = run.finished_at
            source.consecutive_failures = 0
            source.health_status = HealthStatus.healthy
            source.next_due_at = _next_due(source, run.finished_at)
            await session.flush()
            return IngestOutcome(
                source_id=source.id,
                run_id=run.id,
                status="not_modified",
            )
        if result.error_class or not result.ok:
            category = result.error_class or "http_error"
            message = result.error_message or f"Source returned HTTP {result.http_status}"
            await _record_failure(
                session,
                source,
                run,
                category,
                message,
                now_utc(),
                result.http_status,
            )
            return IngestOutcome(
                source_id=source.id,
                run_id=run.id,
                status="failed",
                error_category=category,
                error_message=message,
            )
        candidates = adapter.parse(source_config, result)
        if len(candidates) > 5000:
            raise ValueError("Adapter returned more than 5000 candidates; refusing partial import")
        candidates = [candidate for candidate in candidates if candidate.title.strip()]
        run.records_seen = len(candidates)
        run.scan_complete = result.scan_complete
        revisions: list[uuid.UUID] = []
        for candidate in candidates:
            opportunity, created_revisions = await _upsert_candidate(
                session, source, run, result, candidate, profile, now
            )
            revisions.extend(revision.id for revision in created_revisions)
        if adapter.supports_closure and result.scan_complete:
            closure_revisions = await _apply_absence_closure(session, source, run, now)
            revisions.extend(revision.id for revision in closure_revisions)
        cache = dict(source.config_json or {})
        cache["http_cache"] = {
            "etag": result.etag,
            "last_modified": result.last_modified,
        }
        source.config_json = cache
        source.last_success_at = now_utc()
        source.consecutive_failures = 0
        source.health_status = HealthStatus.healthy
        source.last_error_at = None
        source.last_error_category = None
        source.last_error_redacted = None
        source.next_due_at = _next_due(source, source.last_success_at)
        run.status = "success"
        run.finished_at = now_utc()
        run.scan_complete = result.scan_complete
        await session.flush()
        return IngestOutcome(
            source_id=source.id,
            run_id=run.id,
            status="success",
            records_seen=run.records_seen,
            created=run.records_created,
            updated=run.records_updated,
            skipped=run.records_skipped,
            scan_complete=run.scan_complete,
            revisions=revisions,
        )
    except SQLAlchemyError:
        raise
    except Exception as exc:
        category, message = _safe_error(exc)
        await _record_failure(session, source, run, category, message, now_utc())
        return IngestOutcome(
            source_id=source.id,
            run_id=run.id,
            status="failed",
            error_category=category,
            error_message=message,
        )
    finally:
        if fetcher is not None:
            await fetcher.close()
