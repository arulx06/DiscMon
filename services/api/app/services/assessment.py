from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment
from app.db.models.enums import EmploymentStage
from app.db.models.opportunity import Opportunity, OpportunitySource
from app.db.models.user import UserProfile
from app.services.scoring import RULES_VERSION, AssessmentResult, assess


async def get_or_create_profile(session: AsyncSession) -> UserProfile:
    profile = await session.scalar(select(UserProfile).order_by(UserProfile.created_at).limit(1))
    if profile is None:
        profile = UserProfile(
            employment_stage=EmploymentStage.prejoin,
            student_status=False,
            home_country="IN",
            preferred_countries=["IN"],
            relocation_allowed=False,
            categories=[
                "backend",
                "distributed systems",
                "cloud",
                "platform",
                "sre",
                "databases",
                "security",
                "open source",
            ],
            skills=["python", "typescript", "postgresql", "linux", "distributed systems"],
            ignore_terms=[],
        )
        session.add(profile)
        await session.flush()
    return profile


async def evidence_refs_for(session: AsyncSession, opportunity_id: uuid.UUID) -> list[dict]:
    from app.db.models.evidence import RawEvidence

    rows = (
        await session.execute(
            select(OpportunitySource, RawEvidence)
            .join(RawEvidence, RawEvidence.id == OpportunitySource.raw_evidence_id)
            .where(OpportunitySource.opportunity_id == opportunity_id)
            .order_by(RawEvidence.fetched_at.desc())
            .limit(5)
        )
    ).all()
    refs = []
    for link, evidence in rows:
        refs.append(
            {
                "url": evidence.source_url,
                "observed_at": evidence.fetched_at.isoformat() if evidence.fetched_at else None,
                "excerpt": evidence.extracted_text_excerpt,
                "source_id": str(link.source_id),
                "content_hash": evidence.content_hash,
            }
        )
    return refs


async def assess_opportunity(
    session: AsyncSession,
    opportunity: Opportunity,
    profile: UserProfile,
    revision_id: uuid.UUID | None,
) -> tuple[Assessment, AssessmentResult]:
    result = assess(opportunity, profile)
    evidence_refs = await evidence_refs_for(session, opportunity.id)
    assessment = Assessment(
        opportunity_id=opportunity.id,
        revision_id=revision_id,
        rules_version=RULES_VERSION,
        profile_version=profile.profile_version,
        score_total=result.score_total,
        factor_scores_json=result.factors,
        hard_gate_status=result.hard_gate_status,
        professional_eligibility_state=opportunity.professional_eligibility,
        india_eligibility_state=opportunity.india_eligibility,
        evidence_refs_json=evidence_refs,
        confidence=result.confidence,
        recommended_bucket=result.recommended_bucket,
        recommendation_reason=result.recommendation_reason,
        is_ai_assisted=False,
    )
    session.add(assessment)
    await session.flush()
    return assessment, result
