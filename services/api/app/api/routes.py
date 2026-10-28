from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_owner
from app.api.serializers import jsonable, opportunity_card
from app.collectors import get_adapter
from app.collectors.http import FetchPolicy, SafeFetcher, validate_target
from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.audit import AuditEvent
from app.db.models.digest import Digest
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import (
    ApprovalStatus,
    DeadlinePrecision,
    DigestKind,
    EmploymentStage,
    HealthStatus,
    JobKind,
    JobState,
    LegalReviewStatus,
    LifeState,
    Officialness,
    RecommendationBucket,
    SourceKind,
    UserDecision,
)
from app.db.models.evidence import RawEvidence
from app.db.models.job import Job
from app.db.models.opportunity import (
    Opportunity,
    OpportunityRevision,
    OpportunitySource,
    Organization,
)
from app.db.models.review import Review
from app.db.models.source import Source, SourceRun
from app.db.models.user import UserProfile
from app.db.session import get_db
from app.schemas.collector import SourceConfig
from app.services.assessment import get_or_create_profile
from app.services.digests import (
    _deadline_label,
    current_brief_markdown,
    generate_digest,
)
from app.services.discovery import discovery_enabled, promote_candidate
from app.services.exports import (
    analysis_brief,
    export_row,
    opportunities_csv,
    opportunities_ics,
)
from app.services.queue import enqueue_job, enqueue_source_job, queued_depth
from app.services.sheets import enqueue_sheet_upsert
from app.services.time import days_until, now_utc
from app.services.urls import canonicalize_url, domain_of, is_http_url

router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])


def _latest_assessment_id():
    return (
        select(Assessment.id)
        .where(Assessment.opportunity_id == Opportunity.id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .limit(1)
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _profile_dict(profile: UserProfile) -> dict:
    return {
        "id": str(profile.id),
        "employment_stage": profile.employment_stage.value,
        "student_status": profile.student_status,
        "home_country": profile.home_country,
        "preferred_countries": profile.preferred_countries,
        "relocation_allowed": profile.relocation_allowed,
        "categories": profile.categories,
        "skills": profile.skills,
        "ignore_terms": profile.ignore_terms,
        "desired_yoe_min": profile.desired_yoe_min,
        "desired_yoe_max": profile.desired_yoe_max,
        "quiet_hours_start": profile.quiet_hours_start,
        "quiet_hours_end": profile.quiet_hours_end,
        "timezone": profile.timezone,
        "alert_channels": profile.alert_channels,
        "max_immediate_alerts_per_week": profile.max_immediate_alerts_per_week,
        "scoring_version": profile.scoring_version,
        "profile_version": profile.profile_version,
    }


@router.get("/profile")
async def get_profile(session: AsyncSession = Depends(get_db)) -> dict:
    profile = await get_or_create_profile(session)
    await session.commit()
    return _profile_dict(profile)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    profile = await get_or_create_profile(session)
    before = _profile_dict(profile)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None:
            setattr(profile, field, value)
    if profile.home_country:
        profile.home_country = profile.home_country.upper()
    profile.preferred_countries = [
        str(country).upper()[:2] for country in profile.preferred_countries
    ]
    if (
        profile.desired_yoe_min is not None
        and profile.desired_yoe_max is not None
        and profile.desired_yoe_min > profile.desired_yoe_max
    ):
        raise HTTPException(
            status_code=400,
            detail="desired_yoe_min cannot exceed desired_yoe_max",
        )
    profile.profile_version += 1
    session.add(
        AuditEvent(
            actor="owner",
            event_type="profile.updated",
            entity_type="profile",
            entity_id=profile.id,
            before_json=before,
            after_json=_profile_dict(profile),
        )
    )
    await session.commit()
    return _profile_dict(profile)


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_db)) -> dict:
    health_rows = (
        await session.execute(
            select(Source.health_status, func.count(Source.id)).group_by(Source.health_status)
        )
    ).all()
    source_health = {status.value: count for status, count in health_rows}
    latest = _latest_assessment_id()
    bucket_rows = (
        await session.execute(
            select(Assessment.recommended_bucket, func.count(Assessment.id))
            .where(Assessment.id == latest)
            .group_by(Assessment.recommended_bucket)
        )
    ).all()
    buckets = {bucket.value: count for bucket, count in bucket_rows}
    failing_sources = (
        (
            await session.execute(
                select(Source)
                .where(Source.health_status == HealthStatus.failing)
                .order_by(Source.last_error_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    recent_failed_runs = (
        await session.execute(
            select(SourceRun, Source.name)
            .join(Source, Source.id == SourceRun.source_id)
            .where(SourceRun.status == "failed")
            .order_by(SourceRun.started_at.desc())
            .limit(10)
        )
    ).all()
    job_counts = await queued_depth(session)
    pending_alerts = await session.scalar(
        select(func.count(Alert.id)).where(Alert.status == "pending")
    )
    active_opportunities = await session.scalar(
        select(func.count(Opportunity.id)).where(
            Opportunity.life_state.in_([LifeState.open, LifeState.upcoming]),
            Opportunity.is_fixture.is_(False),
        )
    )
    return {
        "active_opportunities": active_opportunities or 0,
        "source_health": source_health,
        "buckets": buckets,
        "failing_sources": [
            {
                "id": str(source.id),
                "name": source.name,
                "last_error": source.last_error_redacted,
                "last_error_at": jsonable(source.last_error_at),
                "consecutive_failures": source.consecutive_failures,
            }
            for source in failing_sources
        ],
        "recent_failed_runs": [
            {
                "id": str(run.id),
                "source": name,
                "started_at": jsonable(run.started_at),
                "error_category": run.error_category,
                "error": run.error_message_redacted,
            }
            for run, name in recent_failed_runs
        ],
        "jobs": job_counts,
        "pending_alerts": pending_alerts or 0,
        "scan_is_partial": bool(failing_sources),
    }


@router.get("/opportunities")
async def list_opportunities(
    session: AsyncSession = Depends(get_db),
    bucket: RecommendationBucket | None = None,
    life_state: LifeState | None = None,
    decision: UserDecision | None = None,
    source_id: uuid.UUID | None = None,
    search: str | None = None,
    include_fixtures: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    latest = _latest_assessment_id()
    statement = (
        select(Opportunity, Organization, Assessment)
        .outerjoin(Organization, Organization.id == Opportunity.organization_id)
        .outerjoin(Assessment, Assessment.id == latest)
        .where(Opportunity.is_fixture.is_(include_fixtures))
    )
    if bucket is not None:
        statement = statement.where(Assessment.recommended_bucket == bucket)
    if life_state is not None:
        statement = statement.where(Opportunity.life_state == life_state)
    if decision is not None:
        statement = statement.where(Opportunity.user_decision == decision)
    if source_id is not None:
        statement = statement.where(
            Opportunity.id.in_(
                select(OpportunitySource.opportunity_id).where(
                    OpportunitySource.source_id == source_id
                )
            )
        )
    if search:
        pattern = f"%{search.strip()[:120]}%"
        statement = statement.where(
            or_(
                Opportunity.title.ilike(pattern),
                Opportunity.description_summary.ilike(pattern),
                Organization.canonical_name.ilike(pattern),
            )
        )
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = (
        await session.execute(
            statement.order_by(
                Assessment.score_total.desc().nullslast(),
                Opportunity.last_seen_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "items": [
            opportunity_card(opportunity, organization, assessment)
            for opportunity, organization, assessment in rows
        ],
    }


WATCHLIST_GROUPS = [
    ("watch", "Watch", [UserDecision.watch]),
    ("prepare", "Prepare", [UserDecision.prepare]),
    ("research", "Research", [UserDecision.research]),
    ("apply", "Ready to apply", [UserDecision.apply]),
    ("applied", "Applied or interviewing", [UserDecision.applied, UserDecision.interviewing]),
    (
        "archive",
        "Archive",
        [UserDecision.ignored, UserDecision.completed, UserDecision.rejected],
    ),
]


@router.get("/watchlist")
async def watchlist(session: AsyncSession = Depends(get_db)) -> dict:
    decisions = [decision for _, _, values in WATCHLIST_GROUPS for decision in values]
    latest = _latest_assessment_id()
    rows = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(Opportunity.user_decision.in_(decisions))
        )
    ).all()
    ids = [opportunity.id for opportunity, _, _ in rows]
    latest_reviews: dict[uuid.UUID, Review] = {}
    if ids:
        reviews = (
            (
                await session.execute(
                    select(Review)
                    .where(Review.opportunity_id.in_(ids))
                    .order_by(Review.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        for review in reviews:
            latest_reviews.setdefault(review.opportunity_id, review)
    now = now_utc()
    grouped: dict[str, list[dict]] = {key: [] for key, _, _ in WATCHLIST_GROUPS}
    group_by_decision = {
        decision: key
        for key, _, decisions_group in WATCHLIST_GROUPS
        for decision in decisions_group
    }
    followups_due = 0
    for opportunity, organization, assessment in rows:
        latest_review = latest_reviews.get(opportunity.id)
        followup = latest_review.followup_due_at if latest_review else None
        if followup is not None and followup <= now:
            followups_due += 1
        item = opportunity_card(opportunity, organization, assessment)
        item["followup_due_at"] = jsonable(followup)
        item["followup_is_due"] = bool(followup is not None and followup <= now)
        grouped[group_by_decision[opportunity.user_decision]].append(item)
    groups = []
    for key, title, _ in WATCHLIST_GROUPS:
        items = grouped[key]
        items.sort(
            key=lambda item: (
                item["followup_due_at"] is None,
                item["followup_due_at"] or "",
                -(item["score"] or 0),
            )
        )
        groups.append({"key": key, "title": title, "items": items, "total": len(items)})
    return {"groups": groups, "followups_due": followups_due}


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    latest = _latest_assessment_id()
    row = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(Opportunity.id == opportunity_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opportunity, organization, assessment = row
    revisions = (
        (
            await session.execute(
                select(OpportunityRevision)
                .where(OpportunityRevision.opportunity_id == opportunity.id)
                .order_by(OpportunityRevision.revision_number.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    source_rows = (
        await session.execute(
            select(OpportunitySource, Source, RawEvidence)
            .join(Source, Source.id == OpportunitySource.source_id)
            .outerjoin(RawEvidence, RawEvidence.id == OpportunitySource.raw_evidence_id)
            .where(OpportunitySource.opportunity_id == opportunity.id)
        )
    ).all()
    alerts = (
        (
            await session.execute(
                select(Alert)
                .where(Alert.opportunity_id == opportunity.id)
                .order_by(Alert.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    latest_review = await session.scalar(
        select(Review)
        .where(Review.opportunity_id == opportunity.id)
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    return {
        **opportunity_card(opportunity, organization, assessment),
        "application_url": opportunity.application_url,
        "description": opportunity.description_summary,
        "requirements": opportunity.requirements_summary,
        "qualification": jsonable(opportunity.eligibility_reasons_json),
        "assessment": (
            {
                "score": assessment.score_total,
                "bucket": assessment.recommended_bucket.value,
                "confidence": assessment.confidence,
                "hard_gate": assessment.hard_gate_status.value,
                "factors": jsonable(assessment.factor_scores_json),
                "reason": assessment.recommendation_reason,
                "rules_version": assessment.rules_version,
                "profile_version": assessment.profile_version,
                "evidence": jsonable(assessment.evidence_refs_json),
                "created_at": jsonable(assessment.created_at),
            }
            if assessment
            else None
        ),
        "revisions": [
            {
                "id": str(revision.id),
                "number": revision.revision_number,
                "type": revision.revision_type.value,
                "observed_at": jsonable(revision.observed_at),
                "diff": jsonable(revision.material_diff_json),
                "hash": revision.normalized_hash,
                "evidence_ids": revision.evidence_ids,
            }
            for revision in revisions
        ],
        "sources": [
            {
                "source_id": str(source.id),
                "source_name": source.name,
                "source_kind": source.source_kind.value,
                "officialness": source.officialness.value,
                "item_url": link.source_item_url,
                "first_seen_at": jsonable(link.first_seen_at),
                "last_seen_at": jsonable(link.last_seen_at),
                "absence_count": link.absence_count,
                "evidence": (
                    {
                        "url": evidence.source_url,
                        "fetched_at": jsonable(evidence.fetched_at),
                        "excerpt": evidence.extracted_text_excerpt,
                    }
                    if evidence
                    else None
                ),
            }
            for link, source, evidence in source_rows
        ],
        "alerts": [
            {
                "id": str(alert.id),
                "channel": alert.channel,
                "kind": alert.alert_kind.value,
                "status": alert.status.value,
                "sent_at": jsonable(alert.sent_at),
                "scheduled_for": jsonable(alert.scheduled_for),
            }
            for alert in alerts
        ],
        "notes": opportunity.owner_notes,
        "next_action": opportunity.next_action,
        "followup_due_at": jsonable(latest_review.followup_due_at if latest_review else None),
    }


class ReviewRequest(BaseModel):
    decision: UserDecision
    note: str | None = Field(default=None, max_length=4000)
    next_action: str | None = Field(default=None, max_length=1000)
    followup_due_at: datetime | None = None


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_kind: SourceKind
    root_url: str = Field(min_length=1, max_length=2048)
    config_json: dict[str, object] = Field(default_factory=dict)
    officialness: Officialness = Officialness.unknown
    enabled: bool = False
    approval_status: ApprovalStatus = ApprovalStatus.candidate
    legal_review_status: LegalReviewStatus = LegalReviewStatus.pending
    interval_hours: float = Field(default=24, ge=1, le=8760)
    schedule_cron: str | None = Field(default=None, max_length=64)


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    root_url: str | None = Field(default=None, min_length=1, max_length=2048)
    config_json: dict[str, object] | None = None
    officialness: Officialness | None = None
    enabled: bool | None = None
    approval_status: ApprovalStatus | None = None
    legal_review_status: LegalReviewStatus | None = None
    interval_hours: float | None = Field(default=None, ge=1, le=8760)
    schedule_cron: str | None = Field(default=None, max_length=64)


class ProfileUpdate(BaseModel):
    employment_stage: EmploymentStage | None = None
    student_status: bool | None = None
    home_country: str | None = Field(default=None, min_length=2, max_length=2)
    preferred_countries: list[str] | None = Field(default=None, max_length=20)
    relocation_allowed: bool | None = None
    categories: list[str] | None = Field(default=None, max_length=40)
    skills: list[str] | None = Field(default=None, max_length=80)
    ignore_terms: list[str] | None = Field(default=None, max_length=80)
    desired_yoe_min: int | None = Field(default=None, ge=0, le=50)
    desired_yoe_max: int | None = Field(default=None, ge=0, le=50)
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = Field(default=None, max_length=64)
    alert_channels: list[str] | None = Field(default=None, max_length=10)
    max_immediate_alerts_per_week: int | None = Field(default=None, ge=0, le=50)


class DiscoveryDecision(BaseModel):
    decision: ApprovalStatus
    notes: str | None = Field(default=None, max_length=2000)


class InspectUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/opportunities/{opportunity_id}/revisions")
async def opportunity_revisions(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    revisions = (
        (
            await session.execute(
                select(OpportunityRevision)
                .where(OpportunityRevision.opportunity_id == opportunity.id)
                .order_by(OpportunityRevision.revision_number.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(revision.id),
                "revision_number": revision.revision_number,
                "type": revision.revision_type.value,
                "observed_at": jsonable(revision.observed_at),
                "normalized_hash": revision.normalized_hash,
                "material_diff": jsonable(revision.material_diff_json),
                "evidence_ids": revision.evidence_ids,
            }
            for revision in revisions
        ]
    }


@router.post("/opportunities/{opportunity_id}/review")
async def review_opportunity(
    opportunity_id: uuid.UUID,
    body: ReviewRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    before = opportunity.user_decision.value
    review = Review(
        opportunity_id=opportunity.id,
        decision=body.decision,
        previous_decision=opportunity.user_decision,
        note=body.note,
        followup_due_at=body.followup_due_at,
        actor="owner",
    )
    session.add(review)
    opportunity.user_decision = body.decision
    if body.note is not None:
        opportunity.owner_notes = body.note
    if body.next_action is not None:
        opportunity.next_action = body.next_action.strip() or None
    await enqueue_sheet_upsert(session, opportunity.id)
    session.add(
        AuditEvent(
            actor="owner",
            event_type="opportunity.review",
            entity_type="opportunity",
            entity_id=opportunity.id,
            before_json={"decision": before},
            after_json={
                "decision": body.decision.value,
                "has_next_action": bool(opportunity.next_action),
                "followup_due_at": jsonable(body.followup_due_at),
            },
        )
    )
    await session.commit()
    return {"id": str(review.id), "decision": body.decision.value}


@router.post("/opportunities/{opportunity_id}/rescore")
async def rescore_opportunity(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    job_id = await enqueue_job(
        session,
        JobKind.rescore,
        f"rescore:{opportunity.id}:{uuid.uuid4().hex}",
        payload_json={"opportunity_id": str(opportunity.id)},
    )
    session.add(
        AuditEvent(
            actor="owner",
            event_type="opportunity.rescore_queued",
            entity_type="opportunity",
            entity_id=opportunity.id,
            after_json={"job_id": str(job_id)},
        )
    )
    await session.commit()
    return {"job_id": str(job_id), "opportunity_id": str(opportunity.id)}


@router.get("/opportunities/{opportunity_id}/brief")
async def opportunity_brief(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    latest = _latest_assessment_id()
    row = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(Opportunity.id == opportunity_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opportunity, organization, assessment = row
    return {"markdown": analysis_brief(opportunity, organization, assessment)}


@router.get("/deadlines")
async def list_deadlines(
    session: AsyncSession = Depends(get_db),
    horizon_days: int = Query(default=90, ge=1, le=365),
    include_fixtures: bool = False,
) -> dict:
    now = now_utc()
    today = now.date()
    horizon = today + timedelta(days=horizon_days)
    horizon_at = now + timedelta(days=horizon_days)
    latest = _latest_assessment_id()
    deadline_condition = or_(
        and_(
            Opportunity.deadline_at.is_not(None),
            Opportunity.deadline_at <= horizon_at,
            Opportunity.deadline_at >= now,
        ),
        and_(
            Opportunity.deadline_at.is_(None),
            Opportunity.deadline_on.is_not(None),
            Opportunity.deadline_on >= today,
            Opportunity.deadline_on <= horizon,
        ),
        and_(
            Opportunity.deadline_precision == DeadlinePrecision.month_only,
            Opportunity.deadline_on.is_not(None),
            Opportunity.deadline_on >= today.replace(day=1),
            Opportunity.deadline_on <= horizon,
        ),
    )
    rows = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(
                Opportunity.is_fixture.is_(include_fixtures),
                Opportunity.life_state.in_([LifeState.open, LifeState.upcoming]),
                deadline_condition,
            )
            .order_by(
                Opportunity.deadline_at.asc().nullslast(),
                Opportunity.deadline_on.asc().nullslast(),
            )
        )
    ).all()
    items = []
    for opportunity, organization, assessment in rows:
        items.append(
            {
                **opportunity_card(opportunity, organization, assessment),
                "deadline_label": _deadline_label(opportunity),
                "days_until_deadline": days_until(
                    opportunity.deadline_at or opportunity.deadline_on
                ),
            }
        )
    return {"total": len(items), "items": items}


@router.get("/deadlines.ics")
async def deadlines_ics(
    session: AsyncSession = Depends(get_db),
    include_fixtures: bool = False,
) -> Response:
    opportunities = (
        (
            await session.execute(
                select(Opportunity)
                .where(
                    Opportunity.is_fixture.is_(include_fixtures),
                    Opportunity.life_state.in_([LifeState.open, LifeState.upcoming]),
                    Opportunity.deadline_precision.in_(
                        [DeadlinePrecision.exact, DeadlinePrecision.date_only]
                    ),
                )
                .order_by(Opportunity.deadline_at.asc().nullslast(), Opportunity.deadline_on)
            )
        )
        .scalars()
        .all()
    )
    return Response(
        content=opportunities_ics(list(opportunities)),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="discmon-deadlines.ics"'},
    )


@router.get("/digests")
async def list_digests(
    session: AsyncSession = Depends(get_db),
    kind: DigestKind | None = None,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(Digest).order_by(Digest.generated_at.desc())
    if kind is not None:
        statement = statement.where(Digest.digest_kind == kind)
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    digests = (await session.execute(statement.offset(offset).limit(limit))).scalars().all()
    return {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(digest.id),
                "kind": digest.digest_kind.value,
                "period_start": jsonable(digest.period_start),
                "period_end": jsonable(digest.period_end),
                "generated_at": jsonable(digest.generated_at),
                "sent_status": digest.sent_status,
                "reviewed_at": jsonable(digest.reviewed_at),
                "opportunity_count": len(digest.opportunity_ids or []),
            }
            for digest in digests
        ],
    }


@router.post("/digests/generate")
async def create_digest(
    session: AsyncSession = Depends(get_db),
    kind: DigestKind = DigestKind.daily,
) -> dict:
    digest, created = await generate_digest(session, kind)
    if created:
        session.add(
            AuditEvent(
                actor="owner",
                event_type="digest.generated",
                entity_type="digest",
                entity_id=digest.id,
                after_json={
                    "kind": digest.digest_kind.value,
                    "period_start": jsonable(digest.period_start),
                    "period_end": jsonable(digest.period_end),
                },
            )
        )
    await session.commit()
    return {
        "id": str(digest.id),
        "kind": digest.digest_kind.value,
        "created": created,
        "period_start": jsonable(digest.period_start),
        "period_end": jsonable(digest.period_end),
        "opportunity_ids": digest.opportunity_ids,
    }


@router.get("/digests/{digest_id}")
async def get_digest(
    digest_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    digest = await session.get(Digest, digest_id)
    if digest is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    return {
        "id": str(digest.id),
        "kind": digest.digest_kind.value,
        "period_start": jsonable(digest.period_start),
        "period_end": jsonable(digest.period_end),
        "generated_at": jsonable(digest.generated_at),
        "sent_status": digest.sent_status,
        "reviewed_at": jsonable(digest.reviewed_at),
        "content_md": digest.content_md,
        "content_json": jsonable(digest.content_json),
        "opportunity_ids": digest.opportunity_ids,
    }


@router.post("/digests/{digest_id}/reviewed")
async def mark_digest_reviewed(
    digest_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    digest = await session.get(Digest, digest_id)
    if digest is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    if digest.reviewed_at is None:
        digest.reviewed_at = now_utc()
        digest.sent_status = "reviewed"
        session.add(
            AuditEvent(
                actor="owner",
                event_type="digest.reviewed",
                entity_type="digest",
                entity_id=digest.id,
                after_json={"reviewed_at": jsonable(digest.reviewed_at)},
            )
        )
    await session.commit()
    return {"id": str(digest.id), "reviewed_at": jsonable(digest.reviewed_at)}


@router.get("/export/opportunities.csv")
async def export_opportunities_csv(
    session: AsyncSession = Depends(get_db),
    include_fixtures: bool = False,
) -> Response:
    latest = _latest_assessment_id()
    rows = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(Opportunity.is_fixture.is_(include_fixtures))
            .order_by(
                Assessment.score_total.desc().nullslast(),
                Opportunity.last_seen_at.desc(),
            )
        )
    ).all()
    content = opportunities_csv(
        [
            export_row(opportunity, organization, assessment)
            for opportunity, organization, assessment in rows
        ]
    )
    session.add(
        AuditEvent(
            actor="owner",
            event_type="data.export",
            entity_type="opportunity",
            after_json={"format": "csv", "count": len(rows)},
        )
    )
    await session.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="discmon-opportunities.csv"'},
    )


@router.get("/export/brief.md")
async def export_brief_markdown(session: AsyncSession = Depends(get_db)) -> Response:
    content = await current_brief_markdown(session, DigestKind.weekly)
    session.add(
        AuditEvent(
            actor="owner",
            event_type="data.export",
            entity_type="digest",
            after_json={"format": "markdown", "kind": "weekly"},
        )
    )
    await session.commit()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="discmon-weekly-brief.md"'},
    )


def _run_summary(run: SourceRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "status": run.status,
        "scan_complete": run.scan_complete,
        "http_status": run.http_status,
        "records_seen": run.records_seen,
        "records_created": run.records_created,
        "records_updated": run.records_updated,
        "records_skipped": run.records_skipped,
        "error_category": run.error_category,
        "error": run.error_message_redacted,
        "started_at": jsonable(run.started_at),
        "finished_at": jsonable(run.finished_at),
    }


def _source_summary(source: Source, last_run: SourceRun | None = None) -> dict:
    return {
        "id": str(source.id),
        "name": source.name,
        "kind": source.source_kind.value,
        "root_url": source.root_url,
        "enabled": source.enabled,
        "officialness": source.officialness.value,
        "approval_status": source.approval_status.value,
        "legal_review_status": source.legal_review_status.value,
        "health": source.health_status.value,
        "consecutive_failures": source.consecutive_failures,
        "interval_hours": float(source.interval_hours),
        "schedule_cron": source.schedule_cron,
        "last_attempt_at": jsonable(source.last_attempt_at),
        "last_success_at": jsonable(source.last_success_at),
        "last_error": source.last_error_redacted,
        "next_due_at": jsonable(source.next_due_at),
        "last_run": _run_summary(last_run),
    }


async def _validate_source_root(root_url: str) -> None:
    if not is_http_url(root_url):
        raise HTTPException(status_code=400, detail="Source root URL must be http(s)")
    host = domain_of(root_url)
    if not host:
        raise HTTPException(status_code=400, detail="Source root URL must include a host")
    try:
        await validate_target(
            root_url,
            FetchPolicy(
                allowed_hosts={host},
                timeout_seconds=10,
                max_retries=1,
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Source root URL is not fetchable: {type(exc).__name__}",
        ) from exc


def _require_enable_approvals(
    enabled: bool,
    approval_status: ApprovalStatus,
    legal_review_status: LegalReviewStatus,
) -> None:
    if not enabled:
        return
    if (
        approval_status != ApprovalStatus.approved
        or legal_review_status != LegalReviewStatus.approved
    ):
        raise HTTPException(
            status_code=400,
            detail="A source can only be enabled after approval and legal review",
        )


@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_db)) -> dict:
    sources = (await session.execute(select(Source).order_by(Source.name))).scalars().all()
    last_runs: dict[uuid.UUID, SourceRun] = {}
    for source in sources:
        run = await session.scalar(
            select(SourceRun)
            .where(SourceRun.source_id == source.id)
            .order_by(SourceRun.started_at.desc())
            .limit(1)
        )
        if run:
            last_runs[source.id] = run
    return {"items": [_source_summary(source, last_runs.get(source.id)) for source in sources]}


@router.post("/sources", status_code=201)
async def create_source(
    body: SourceCreate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    _require_enable_approvals(body.enabled, body.approval_status, body.legal_review_status)
    await _validate_source_root(body.root_url)
    source = Source(
        name=body.name.strip(),
        source_kind=body.source_kind,
        root_url=body.root_url,
        config_json=body.config_json,
        officialness=body.officialness,
        enabled=body.enabled,
        approval_status=body.approval_status,
        legal_review_status=body.legal_review_status,
        interval_hours=body.interval_hours,
        schedule_cron=body.schedule_cron,
        next_due_at=now_utc() if body.enabled else None,
        health_status=HealthStatus.unknown,
    )
    session.add(source)
    await session.flush()
    session.add(
        AuditEvent(
            actor="owner",
            event_type="source.created",
            entity_type="source",
            entity_id=source.id,
            after_json=_source_summary(source),
        )
    )
    await session.commit()
    return _source_summary(source)


@router.get("/sources/{source_id}")
async def get_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    last_run = await session.scalar(
        select(SourceRun)
        .where(SourceRun.source_id == source.id)
        .order_by(SourceRun.started_at.desc())
        .limit(1)
    )
    return {
        **_source_summary(source, last_run),
        "config_json": source.config_json,
        "rate_limit_json": source.rate_limit_json,
    }


@router.patch("/sources/{source_id}")
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    before = _source_summary(source)
    changes = body.model_dump(exclude_unset=True)
    if "root_url" in changes and changes["root_url"] is not None:
        await _validate_source_root(str(changes["root_url"]))
    proposed_enabled = bool(changes.get("enabled", source.enabled))
    proposed_approval = changes.get("approval_status", source.approval_status)
    proposed_legal = changes.get("legal_review_status", source.legal_review_status)
    _require_enable_approvals(proposed_enabled, proposed_approval, proposed_legal)
    for field, value in changes.items():
        if value is not None or field in {"schedule_cron"}:
            setattr(source, field, value)
    if body.enabled is True and source.next_due_at is None:
        source.next_due_at = now_utc()
    if body.enabled is False:
        source.next_due_at = None
    session.add(
        AuditEvent(
            actor="owner",
            event_type="source.updated",
            entity_type="source",
            entity_id=source.id,
            before_json=before,
            after_json=_source_summary(source),
        )
    )
    await session.commit()
    return _source_summary(source)


@router.delete("/sources/{source_id}")
async def retire_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    before = _source_summary(source)
    source.enabled = False
    source.approval_status = ApprovalStatus.retired
    source.next_due_at = None
    session.add(
        AuditEvent(
            actor="owner",
            event_type="source.retired",
            entity_type="source",
            entity_id=source.id,
            before_json=before,
            after_json=_source_summary(source),
        )
    )
    await session.commit()
    return _source_summary(source)


@router.get("/sources/{source_id}/runs")
async def source_runs(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    runs = (
        (
            await session.execute(
                select(SourceRun)
                .where(SourceRun.source_id == source.id)
                .order_by(SourceRun.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_run_summary(run) for run in runs]}


@router.post("/sources/{source_id}/test")
async def test_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    config = SourceConfig.model_validate(source)
    try:
        adapter = get_adapter(source.source_kind.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="No adapter for this source") from exc
    policy = FetchPolicy(
        allowed_hosts=adapter.allowed_hosts(config),
        timeout_seconds=15,
        max_retries=1,
    )
    try:
        async with SafeFetcher(policy) as fetcher:
            result = await adapter.fetch(config, fetcher)
            candidates = adapter.parse(config, result) if result.ok else []
    except Exception as exc:
        session.add(
            AuditEvent(
                actor="owner",
                event_type="source.tested",
                entity_type="source",
                entity_id=source.id,
                after_json={"ok": False, "error": type(exc).__name__},
            )
        )
        await session.commit()
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": "Preview failed; inspect the run logs and source configuration",
        }
    preview = [
        {
            "external_id": candidate.source_external_id[:120],
            "title": " ".join(candidate.title.split())[:240],
            "organization": (candidate.organization_name or "")[:200],
            "location": (candidate.location_text or "")[:200],
            "opportunity_type": candidate.opportunity_type.value,
            "official_url": candidate.official_url if is_http_url(candidate.official_url) else None,
            "deadline_precision": candidate.deadline_precision.value,
            "deadline_on": candidate.deadline_on.isoformat() if candidate.deadline_on else None,
        }
        for candidate in candidates[:10]
    ]
    outcome = {
        "ok": result.ok and result.error_class is None,
        "http_status": result.http_status,
        "scan_complete": result.scan_complete,
        "error_class": result.error_class,
        "records_seen": len(candidates),
        "preview": preview,
    }
    session.add(
        AuditEvent(
            actor="owner",
            event_type="source.tested",
            entity_type="source",
            entity_id=source.id,
            after_json={
                "ok": outcome["ok"],
                "records_seen": len(candidates),
                "http_status": result.http_status,
            },
        )
    )
    await session.commit()
    return outcome


@router.post("/sources/{source_id}/run")
async def run_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.enabled:
        raise HTTPException(status_code=400, detail="Source is disabled")
    job_id = await enqueue_source_job(session, source.id)
    if job_id is None:
        raise HTTPException(status_code=409, detail="A run is already queued or running")
    session.add(
        AuditEvent(
            actor="owner",
            event_type="source.run_queued",
            entity_type="source",
            entity_id=source.id,
            after_json={"job_id": str(job_id)},
        )
    )
    await session.commit()
    return {"job_id": str(job_id), "source_id": str(source.id)}


@router.get("/alerts")
async def list_alerts(
    session: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    statement = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(Alert.status == status)
    alerts = (await session.execute(statement)).scalars().all()
    return {
        "items": [
            {
                "id": str(alert.id),
                "channel": alert.channel,
                "kind": alert.alert_kind.value,
                "status": alert.status.value,
                "scheduled_for": jsonable(alert.scheduled_for),
                "sent_at": jsonable(alert.sent_at),
                "created_at": jsonable(alert.created_at),
                "payload": jsonable(alert.payload_json),
                "error": alert.last_error_redacted,
            }
            for alert in alerts
        ]
    }


@router.get("/jobs")
async def list_jobs(session: AsyncSession = Depends(get_db)) -> dict:
    jobs = (
        (await session.execute(select(Job).order_by(Job.created_at.desc()).limit(100)))
        .scalars()
        .all()
    )
    return {
        "active": await queued_depth(session),
        "items": [
            {
                "id": str(job.id),
                "kind": job.kind.value,
                "state": job.state.value,
                "source_id": str(job.source_id) if job.source_id else None,
                "attempts": job.attempts,
                "available_at": jsonable(job.available_at),
                "last_error": job.last_error_redacted,
                "created_at": jsonable(job.created_at),
            }
            for job in jobs
        ],
    }


@router.get("/audit")
async def list_audit(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    events = (
        (
            await session.execute(
                select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(event.id),
                "actor": event.actor,
                "event_type": event.event_type,
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id) if event.entity_id else None,
                "before": jsonable(event.before_json),
                "after": jsonable(event.after_json),
                "timestamp": jsonable(event.timestamp),
            }
            for event in events
        ]
    }


@router.post("/discovery/sources/{source_id}/run", status_code=202)
async def run_source_discovery(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.enabled:
        raise HTTPException(status_code=400, detail="Source is disabled")
    if not discovery_enabled(source):
        raise HTTPException(status_code=400, detail="Discovery is not enabled for this source")
    active = await session.scalar(
        select(Job.id)
        .where(
            Job.source_id == source.id,
            Job.kind == JobKind.discover_source,
            Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait]),
        )
        .limit(1)
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="A discovery scan is already queued or running")
    stamp = now_utc().strftime("%Y%m%d%H%M%S")
    job_id = await enqueue_job(
        session,
        JobKind.discover_source,
        f"discover:{source.id}:{stamp}",
        source_id=source.id,
    )
    session.add(
        AuditEvent(
            actor="owner",
            event_type="discovery.run_queued",
            entity_type="source",
            entity_id=source.id,
            after_json={"job_id": str(job_id)},
        )
    )
    await session.commit()
    return {"job_id": str(job_id), "source_id": str(source.id)}


@router.get("/discovery/candidates")
async def list_discovery_candidates(
    session: AsyncSession = Depends(get_db),
    status: ApprovalStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    statement = select(DiscoveryCandidate).order_by(DiscoveryCandidate.discovered_at.desc())
    if status is not None:
        statement = statement.where(DiscoveryCandidate.approval_status == status)
    candidates = (await session.execute(statement.limit(limit))).scalars().all()
    return {
        "items": [
            {
                "id": str(candidate.id),
                "url": candidate.candidate_url,
                "discovered_at": jsonable(candidate.discovered_at),
                "candidate_type": candidate.candidate_type,
                "suggested_adapter": (
                    candidate.suggested_adapter.value if candidate.suggested_adapter else None
                ),
                "officialness_guess": candidate.officialness_guess.value,
                "approval_status": candidate.approval_status.value,
                "legal_review_status": candidate.legal_review_status.value,
                "promoted_source_id": (
                    str(candidate.promoted_source_id)
                    if candidate.promoted_source_id
                    else None
                ),
                "notes": candidate.notes,
            }
            for candidate in candidates
        ]
    }


@router.post("/discovery/candidates/{candidate_id}/decision")
async def decide_discovery_candidate(
    candidate_id: uuid.UUID,
    body: DiscoveryDecision,
    session: AsyncSession = Depends(get_db),
) -> dict:
    candidate = await session.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    if body.decision not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected")
    before = candidate.approval_status.value
    candidate.approval_status = body.decision
    candidate.last_checked_at = now_utc()
    if body.notes is not None:
        candidate.notes = body.notes
    session.add(
        AuditEvent(
            actor="owner",
            event_type="discovery.decision",
            entity_type="discovery_candidate",
            entity_id=candidate.id,
            before_json={"approval_status": before},
            after_json={"approval_status": candidate.approval_status.value},
        )
    )
    await session.commit()
    return {
        "id": str(candidate.id),
        "approval_status": candidate.approval_status.value,
    }


@router.post("/discovery/candidates/{candidate_id}/promote", status_code=201)
async def promote_discovery_candidate(
    candidate_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    candidate = await session.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    await _validate_source_root(candidate.candidate_url)
    try:
        source, created = await promote_candidate(session, candidate.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.add(
        AuditEvent(
            actor="owner",
            event_type="discovery.promoted",
            entity_type="source",
            entity_id=source.id,
            after_json={
                "candidate_id": str(candidate.id),
                "created": created,
                "root_url": source.root_url,
            },
        )
    )
    await session.commit()
    return {
        "candidate_id": str(candidate.id),
        "source_id": str(source.id),
        "created": created,
        "source": _source_summary(source),
    }


@router.post("/discovery/inspect-url", status_code=201)
async def inspect_discovery_url(
    body: InspectUrlRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _validate_source_root(body.url)
    canonical = canonicalize_url(body.url)
    existing = await session.scalar(
        select(DiscoveryCandidate).where(DiscoveryCandidate.candidate_url == canonical)
    )
    if existing is not None:
        return {
            "id": str(existing.id),
            "url": existing.candidate_url,
            "created": False,
        }
    candidate = DiscoveryCandidate(
        candidate_url=canonical,
        discovered_at=now_utc(),
        candidate_type="manual_inspection",
        suggested_adapter=SourceKind.static_html,
        officialness_guess=Officialness.unknown,
        approval_status=ApprovalStatus.candidate,
        legal_review_status=LegalReviewStatus.pending,
        notes=body.notes,
    )
    session.add(candidate)
    await session.flush()
    session.add(
        AuditEvent(
            actor="owner",
            event_type="discovery.inspected",
            entity_type="discovery_candidate",
            entity_id=candidate.id,
            after_json={"url": candidate.candidate_url},
        )
    )
    await session.commit()
    return {
        "id": str(candidate.id),
        "url": candidate.candidate_url,
        "created": True,
    }


@router.get("/admin/jobs")
async def admin_jobs(session: AsyncSession = Depends(get_db)) -> dict:
    return await list_jobs(session)


@router.post("/admin/jobs/{job_id}/retry")
async def retry_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state not in {JobState.dead, JobState.retry_wait}:
        raise HTTPException(status_code=400, detail="Only dead or retry-wait jobs can be retried")
    before = job.state.value
    job.state = JobState.queued
    job.attempts = 0
    job.available_at = now_utc()
    job.locked_by = None
    job.lock_expires_at = None
    job.last_error_redacted = None
    session.add(
        AuditEvent(
            actor="owner",
            event_type="job.retried",
            entity_type="job",
            entity_id=job.id,
            before_json={"state": before},
            after_json={"state": job.state.value},
        )
    )
    await session.commit()
    return {"id": str(job.id), "state": job.state.value}


@router.get("/health/sources")
async def source_health(session: AsyncSession = Depends(get_db)) -> dict:
    health_rows = (
        await session.execute(
            select(Source.health_status, func.count(Source.id)).group_by(Source.health_status)
        )
    ).all()
    counts = {status.value: count for status, count in health_rows}
    attention = (
        (
            await session.execute(
                select(Source)
                .where(Source.health_status.in_([HealthStatus.failing, HealthStatus.stale]))
                .order_by(Source.health_status, Source.name)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    last_success = await session.scalar(select(func.max(Source.last_success_at)))
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "attention": [
            {
                "id": str(source.id),
                "name": source.name,
                "health": source.health_status.value,
                "last_error": source.last_error_redacted,
                "last_success_at": jsonable(source.last_success_at),
            }
            for source in attention
        ],
        "last_source_success_at": jsonable(last_success),
    }


@router.get("/system/status")
async def system_status(session: AsyncSession = Depends(get_db)) -> dict:
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    failing = await session.scalar(
        select(func.count(Source.id)).where(Source.health_status == HealthStatus.failing)
    )
    stale = await session.scalar(
        select(func.count(Source.id)).where(Source.health_status == HealthStatus.stale)
    )
    queued = await session.scalar(
        select(func.count(Job.id)).where(
            Job.state.in_([JobState.queued, JobState.running, JobState.retry_wait])
        )
    )
    return {
        "database": "ok" if db_ok else "error",
        "failing_sources": failing or 0,
        "stale_sources": stale or 0,
        "active_jobs": queued or 0,
        "time": jsonable(now_utc()),
    }
