from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.models.enums import (
    EligibilityStatus,
    HardGateStatus,
    OpportunityType,
    RecommendationBucket,
)
from app.db.models.opportunity import Opportunity
from app.db.models.user import UserProfile
from app.services.time import days_until

RULES_VERSION = "v1"

ENGINEERING_KEYWORDS = {
    "backend": 4,
    "back-end": 4,
    "distributed": 5,
    "systems": 4,
    "cloud": 4,
    "infrastructure": 5,
    "platform": 4,
    "sre": 4,
    "reliability": 4,
    "database": 4,
    "storage": 4,
    "networking": 4,
    "security": 4,
    "open source": 5,
    "developer tools": 4,
    "software engineer": 3,
    "ai infrastructure": 5,
    "ml infrastructure": 5,
    "machine learning": 3,
    "data engineering": 3,
}

SCAM_PATTERNS = [
    r"\bpay\s+to\s+apply\b",
    r"\bregistration\s+fee\b",
    r"\btraining\s+fee\b",
    r"\bsecurity\s+deposit\b",
    r"\bunpaid\s+training\b",
    r"\bguaranteed\s+(?:job|placement)\b",
]


@dataclass
class AssessmentResult:
    score_total: int
    factors: dict
    hard_gate_status: HardGateStatus
    recommended_bucket: RecommendationBucket
    recommendation_reason: str
    confidence: float
    evidence_refs: list[dict] = field(default_factory=list)


def _text(opportunity: Opportunity) -> str:
    return " ".join(
        filter(
            None,
            [
                opportunity.title,
                opportunity.description_summary,
                opportunity.requirements_summary,
                opportunity.location_text,
                opportunity.employment_type,
                opportunity.scope,
            ],
        )
    ).lower()


def _engineering_score(opportunity: Opportunity, profile: UserProfile) -> tuple[int, str]:
    text = _text(opportunity)
    score = 5
    matched = []
    for keyword, weight in ENGINEERING_KEYWORDS.items():
        if keyword in text:
            score += weight
            matched.append(keyword)
    profile_terms = {term.lower() for term in (profile.categories or []) + (profile.skills or [])}
    if profile_terms and any(term and term in text for term in profile_terms):
        score += 4
    score = min(score, 25)
    reason = (
        f"Matches engineering signals: {', '.join(matched[:6])}"
        if matched
        else "Limited explicit backend/cloud/systems signal in the source text"
    )
    return score, reason


def _upside_score(opportunity: Opportunity) -> tuple[int, str]:
    base = {
        OpportunityType.fellowship: 16,
        OpportunityType.residency: 17,
        OpportunityType.mentorship: 13,
        OpportunityType.grant: 13,
        OpportunityType.hackathon: 7,
        OpportunityType.competition: 6,
        OpportunityType.founder_programme: 9,
        OpportunityType.job: 11,
        OpportunityType.programme: 11,
        OpportunityType.other: 6,
    }.get(opportunity.opportunity_type, 6)
    compensation = opportunity.monetary_value_json or {}
    if compensation.get("cash"):
        base += 3
    if compensation.get("equity") or compensation.get("credits"):
        base += 1
    if opportunity.credibility_level.value == "high":
        base += 1
    return min(base, 20), (
        "Rare programme type and published value signals; equity/credits are not counted as salary"
    )


def _professional_score(opportunity: Opportunity) -> tuple[int, str]:
    if opportunity.professional_eligibility == EligibilityStatus.verified_yes:
        return 20, "Source explicitly permits working professionals"
    if opportunity.professional_eligibility == EligibilityStatus.unknown:
        return 8, "Professional eligibility is unknown; must remain in verification"
    if opportunity.professional_eligibility == EligibilityStatus.not_applicable:
        return 10, "Professional eligibility is not applicable to this record"
    return 0, "Source explicitly restricts this opportunity to students or another ineligible group"


def _location_score(opportunity: Opportunity, profile: UserProfile) -> tuple[int, str]:
    if opportunity.india_eligibility == EligibilityStatus.verified_yes:
        return 15, "India location or India-inclusive remote allowlist is explicit"
    if opportunity.india_eligibility == EligibilityStatus.unknown:
        return 5, "India eligibility is unknown; never inferred from a remote flag"
    if opportunity.requires_relocation and profile.relocation_allowed:
        return 6, "Non-India role; relocation research is opted in"
    return 0, "Source evidence excludes India and relocation is not opted in"


def _credibility_score(opportunity: Opportunity) -> tuple[int, str]:
    value = {
        "high": (10, "Official source with dated evidence"),
        "medium": (6, "Credible aggregator; primary source follow-up is still required"),
        "low": (2, "Low-confidence source"),
        "unknown": (3, "Source credibility is unverified"),
    }
    score, reason = value.get(opportunity.credibility_level.value, (3, "Unknown credibility"))
    return score, reason


def _timeliness_score(opportunity: Opportunity) -> tuple[int, str]:
    remaining = days_until(opportunity.deadline_at or opportunity.deadline_on)
    if remaining is None:
        return 4, "No published deadline; preparation horizon is unknown"
    if remaining < 0:
        return 0, "Published deadline has passed"
    if remaining <= 7:
        return 10, f"Deadline is within {remaining} day(s)"
    if remaining <= 30:
        return 8, f"Deadline is within {remaining} days"
    if remaining <= 90:
        return 6, f"Deadline is within {remaining} days"
    return 4, "Deadline is more than 90 days away"


def assess(opportunity: Opportunity, profile: UserProfile) -> AssessmentResult:
    text = _text(opportunity)
    hard_exclusions: list[str] = []

    if opportunity.student_only:
        hard_exclusions.append("student-only or graduation-year restriction")
    if opportunity.professional_eligibility == EligibilityStatus.verified_no:
        hard_exclusions.append("source explicitly excludes working professionals")
    if opportunity.india_eligibility == EligibilityStatus.verified_no and not (
        opportunity.requires_relocation and profile.relocation_allowed
    ):
        hard_exclusions.append("source excludes India and relocation is not opted in")
    for term in profile.ignore_terms or []:
        if term and re.search(rf"\b{re.escape(term.lower())}\b", text):
            hard_exclusions.append(f'owner ignore term matched: "{term}"')
    for pattern in SCAM_PATTERNS:
        if re.search(pattern, text):
            hard_exclusions.append("possible paid-to-apply or scam wording")
            break

    relevance, relevance_reason = _engineering_score(opportunity, profile)
    upside, upside_reason = _upside_score(opportunity)
    professional, professional_reason = _professional_score(opportunity)
    location, location_reason = _location_score(opportunity, profile)
    credibility, credibility_reason = _credibility_score(opportunity)
    timeliness, timeliness_reason = _timeliness_score(opportunity)
    total = min(relevance + upside + professional + location + credibility + timeliness, 100)

    factors = {
        "engineering_relevance": {
            "score": relevance,
            "max": 25,
            "reason": relevance_reason,
        },
        "career_upside": {"score": upside, "max": 20, "reason": upside_reason},
        "professional_eligibility": {
            "score": professional,
            "max": 20,
            "reason": professional_reason,
        },
        "location_feasibility": {"score": location, "max": 15, "reason": location_reason},
        "credibility": {"score": credibility, "max": 10, "reason": credibility_reason},
        "timeliness": {"score": timeliness, "max": 10, "reason": timeliness_reason},
    }

    unknown_eligibility = (
        opportunity.professional_eligibility == EligibilityStatus.unknown
        or opportunity.india_eligibility == EligibilityStatus.unknown
    )

    if hard_exclusions:
        hard_gate = HardGateStatus.excluded
        bucket = RecommendationBucket.excluded
        reason = "Hard gate: " + "; ".join(hard_exclusions)
    else:
        hard_gate = (
            HardGateStatus.needs_verification if unknown_eligibility else HardGateStatus.passed
        )
        if unknown_eligibility:
            bucket = RecommendationBucket.needs_verification
            reason = (
                "Deterministic score is for research sorting only; eligibility is unknown and "
                "cannot be labelled Eligible or Apply now"
            )
        elif total >= 85:
            bucket = RecommendationBucket.act_now
            reason = "Verified eligibility and high deterministic score"
        elif total >= 70:
            bucket = RecommendationBucket.prepare_early
            reason = "Strong fit; begin preparation and verify live details"
        elif total >= 50:
            bucket = RecommendationBucket.keep_on_radar
            reason = "Moderate fit; monitor for a material change"
        else:
            bucket = RecommendationBucket.archive
            reason = "Low deterministic fit for the current profile"

    known_dimensions = sum(
        1
        for value in (opportunity.professional_eligibility, opportunity.india_eligibility)
        if value != EligibilityStatus.unknown
    )
    credibility_bonus = {"high": 0.15, "medium": 0.05, "low": -0.1, "unknown": 0.0}.get(
        opportunity.credibility_level.value, 0.0
    )
    confidence = max(0.0, min(0.95, 0.25 + known_dimensions * 0.22 + credibility_bonus))

    return AssessmentResult(
        score_total=total,
        factors=factors,
        hard_gate_status=hard_gate,
        recommended_bucket=bucket,
        recommendation_reason=reason,
        confidence=round(confidence, 3),
    )
