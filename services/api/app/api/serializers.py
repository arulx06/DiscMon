from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from app.db.models.assessment import Assessment
from app.db.models.opportunity import Opportunity, Organization


def jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def opportunity_card(
    opportunity: Opportunity,
    organization: Organization | None,
    assessment: Assessment | None,
) -> dict:
    return {
        "id": str(opportunity.id),
        "title": opportunity.title,
        "organization": organization.canonical_name if organization else None,
        "organization_domain": organization.canonical_domain if organization else None,
        "type": opportunity.opportunity_type.value,
        "bucket": assessment.recommended_bucket.value if assessment else "needs_verification",
        "score": assessment.score_total if assessment else None,
        "confidence": assessment.confidence if assessment else None,
        "professional_eligibility": opportunity.professional_eligibility.value,
        "india_eligibility": opportunity.india_eligibility.value,
        "student_only": opportunity.student_only,
        "location": opportunity.location_text,
        "workplace_type": opportunity.workplace_type,
        "life_state": opportunity.life_state.value,
        "deadline_on": jsonable(opportunity.deadline_on),
        "deadline_at": jsonable(opportunity.deadline_at),
        "deadline_precision": opportunity.deadline_precision.value,
        "compensation": opportunity.compensation_summary,
        "official_url": opportunity.official_url,
        "user_decision": opportunity.user_decision.value,
        "credibility": opportunity.credibility_level.value,
        "first_seen_at": jsonable(opportunity.first_seen_at),
        "last_seen_at": jsonable(opportunity.last_seen_at),
        "last_material_change_at": jsonable(opportunity.last_material_change_at),
        "is_fixture": opportunity.is_fixture,
        "why": assessment.recommendation_reason if assessment else None,
        "hard_gate": assessment.hard_gate_status.value if assessment else None,
    }
