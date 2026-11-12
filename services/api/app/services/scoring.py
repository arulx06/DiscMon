from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.models.enums import (
    EligibilityStatus,
    EmploymentStage,
    HardGateStatus,
    LifeState,
    OpportunityType,
    RecommendationBucket,
)
from app.db.models.opportunity import Opportunity
from app.db.models.user import UserProfile
from app.services.time import days_until

RULES_VERSION = "v3"

ENGINEERING_KEYWORDS = {
    "backend": 4,
    "back-end": 4,
    "distributed": 5,
    "systems": 4,
    "cloud": 4,
    "infrastructure": 5,
    "platform": 4,
    "sre": 4,
    "site reliability": 5,
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

TARGET_ROLE_TITLE_PATTERNS = [
    r"\bbackend\b",
    r"\bback[- ]end\b",
    r"\bdistributed systems?\b",
    r"\b(?:cloud|platform|infrastructure|systems|network|database|storage|security) engineer\b",
    r"\b(?:site reliability|sre)\b",
    r"\bdevops\b",
    r"\bdata engineer\b",
    r"\b(?:machine learning|ml|ai) engineer\b",
    r"\bsoftware engineer\b",
    r"\bsoftware developer\b",
    r"\bfull[- ]stack\b",
    r"\bfounding engineer\b",
    r"\bmember of (?:the )?technical staff\b",
]

ADJACENT_ROLE_TITLE_PATTERNS = [
    r"\bengineering manager\b",
    r"\bmanager\b.*\bengineering\b",
    r"\bengineering\b.*\bmanager\b",
    r"\bhead of engineering\b",
    r"\bdirector of engineering\b",
    r"\bengineering (?:lead|director)\b",
    r"\btechnical program manager\b",
    r"\b(?:solutions|support|qa|test|design|hardware|firmware|electrical|"
    r"mechanical|physical|rtl) (?:engineer|architect)\b",
    r"\bdeveloper advocate\b",
    r"\btechnical writer\b",
    r"\bdata scientist\b",
]

NON_ENGINEERING_ROLE_TITLE_PATTERNS = [
    r"\bcommunications?\b",
    r"\bmarketing\b",
    r"\bsales\b",
    r"\baccounts?\b",
    r"\baccount executive\b",
    r"\bbusiness development\b",
    r"\bpartnerships?\b",
    r"\bseller\b",
    r"\bvendor\b",
    r"\bcustomer success\b",
    r"\bcustomer support\b",
    r"\brecruit(?:er|ing)\b",
    r"\bhuman resources\b",
    r"\bpeople operations\b",
    r"\bfinance\b",
    r"\baccounting\b",
    r"\blegal\b",
    r"\bcompliance\b",
    r"\bcontent\b",
    r"\bbrand\b",
    r"\bsocial media\b",
    r"\bpublic relations\b",
    r"\bcommunity manager\b",
    r"\bdesigner\b",
    r"\bproduct design\b",
    r"\bux\b",
    r"\bui\b",
    r"\bgraphic\b",
]

GENERAL_ENGINEERING_ROLE_TITLE_PATTERNS = [
    r"\b(?:engineer|engineering|developer|architect|technical staff|"
    r"scientist|technologist)\b",
]

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


def _body_text(opportunity: Opportunity) -> str:
    return " ".join(
        filter(
            None,
            [
                opportunity.description_summary,
                opportunity.requirements_summary,
                opportunity.location_text,
                opportunity.employment_type,
                opportunity.scope,
            ],
        )
    ).lower()


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _role_family(title: str) -> tuple[str, str, int, int]:
    target = _first_match(TARGET_ROLE_TITLE_PATTERNS, title)
    if target:
        return "target", target, 16, 25
    non_engineering = _first_match(NON_ENGINEERING_ROLE_TITLE_PATTERNS, title)
    if non_engineering:
        return "non_engineering", non_engineering, 0, 4
    adjacent = _first_match(ADJACENT_ROLE_TITLE_PATTERNS, title)
    if adjacent:
        return "adjacent", adjacent, 8, 14
    general = _first_match(GENERAL_ENGINEERING_ROLE_TITLE_PATTERNS, title)
    if general:
        return "general_engineering", general, 10, 16
    return "non_target", "no engineering role title", 0, 4


def _engineering_score(
    opportunity: Opportunity, profile: UserProfile
) -> tuple[int, str, str]:
    title = opportunity.title.lower()
    role_family, role_hit, base, cap = _role_family(title)
    body = _body_text(opportunity)
    matched = [keyword for keyword in ENGINEERING_KEYWORDS if keyword in body]

    # For fellowships, mentorships, residencies, and grants, the title is often a project
    # or programme name rather than a conventional job title. If it is not explicitly
    # non-engineering and has strong technical body evidence, treat as engineering programme.
    is_programme = opportunity.opportunity_type in {
        OpportunityType.fellowship,
        OpportunityType.residency,
        OpportunityType.mentorship,
        OpportunityType.grant,
    }
    if is_programme and role_family == "non_target" and matched:
        # Check if matched keywords indicate backend/systems/infrastructure/security
        has_target_keywords = any(
            kw in matched
            for kw in (
                "backend",
                "back-end",
                "distributed",
                "systems",
                "cloud",
                "infrastructure",
                "platform",
                "sre",
                "database",
                "security",
                "open source",
                "ai infrastructure",
                "ml infrastructure",
            )
        )
        if has_target_keywords:
            role_family = "target"
            role_hit = f"{opportunity.opportunity_type.value} project"
            base, cap = 16, 25
        else:
            role_family = "general_engineering"
            role_hit = f"{opportunity.opportunity_type.value} project"
            base, cap = 10, 16

    body_cap = {
        "target": 9,
        "general_engineering": 6,
        "adjacent": 4,
        "non_engineering": 3,
        "non_target": 3,
    }[role_family]
    body_score = min(
        sum(ENGINEERING_KEYWORDS[keyword] for keyword in matched),
        body_cap,
    )
    profile_terms = {term.lower() for term in (profile.categories or []) + (profile.skills or [])}
    profile_score = 0
    if role_family == "target":
        profile_score = 3
    elif role_family in {"general_engineering", "adjacent"}:
        profile_score = 2
    elif role_family in {"non_engineering", "non_target"}:
        profile_score = 1
    if not profile_terms or not any(term and term in body for term in profile_terms):
        profile_score = 0
    score = min(base + body_score + profile_score, cap)
    matched_text = ", ".join(matched[:6]) if matched else "no explicit technical keywords"
    if is_programme and role_hit.endswith("project"):
        reason = (
            f"Technical {opportunity.opportunity_type.value} project with engineering scope: "
            f'"{role_hit}". Body evidence: {matched_text}.'
        )
    elif role_family == "target":
        reason = (
            f'Role title matches the target engineering family: "{role_hit}". '
            f"Body evidence: {matched_text}."
        )
    elif role_family == "general_engineering":
        reason = (
            "Role title is a general engineering role, not a target backend family. "
            f"Body evidence: {matched_text}."
        )
    elif role_family == "adjacent":
        reason = (
            f'Role title is adjacent engineering, not a target backend role: "{role_hit}". '
            f"Technical keyword evidence is capped. Body evidence: {matched_text}."
        )
    elif role_family == "non_target":
        reason = (
            "Role title does not identify an engineering role. "
            "Technical keyword mentions in the body do not make this an engineering role. "
            f"Body evidence: {matched_text}."
        )
    else:
        reason = (
            f'Role title is outside backend engineering: "{role_hit}". '
            "Technical keyword mentions in the body do not make this an engineering role. "
            f"Body evidence: {matched_text}."
        )
    return score, reason, role_family


def _upside_score(opportunity: Opportunity) -> tuple[int, str]:
    type_labels = {
        OpportunityType.fellowship: ("fellowship", 16),
        OpportunityType.residency: ("residency", 17),
        OpportunityType.mentorship: ("mentorship programme", 13),
        OpportunityType.grant: ("grant or sponsored programme", 13),
        OpportunityType.hackathon: ("hackathon or time-limited event", 7),
        OpportunityType.competition: ("competition", 6),
        OpportunityType.founder_programme: ("founder programme", 9),
        OpportunityType.job: ("job opening", 11),
        OpportunityType.programme: ("structured programme", 11),
        OpportunityType.other: ("unclassified opportunity", 6),
    }
    label, base = type_labels.get(opportunity.opportunity_type, ("unclassified opportunity", 6))
    signals: list[str] = []
    compensation = opportunity.monetary_value_json or {}
    if compensation.get("cash"):
        base += 3
        signals.append("published compensation")
    if compensation.get("equity") or compensation.get("credits"):
        base += 1
        signals.append("equity or credits mentioned")
    if opportunity.credibility_level.value == "high":
        base += 1
        signals.append("high-credibility source")
    signal_text = "; ".join(signals) if signals else "no additional value signals"
    return min(base, 20), f"Opportunity type: {label}; {signal_text}"


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

    if opportunity.life_state in (LifeState.closed, LifeState.archived):
        hard_exclusions.append(
            f"opportunity is {opportunity.life_state.value}; no longer accepting applications"
        )
    if opportunity.student_only:
        hard_exclusions.append("student-only or graduation-year restriction")
    if opportunity.professional_eligibility == EligibilityStatus.verified_no:
        hard_exclusions.append("source explicitly excludes working professionals")
    if opportunity.india_eligibility == EligibilityStatus.verified_no and not (
        opportunity.requires_relocation and profile.relocation_allowed
    ):
        hard_exclusions.append("source excludes India and relocation is not opted in")
    if opportunity.employment_conflict:
        hard_exclusions.append(
            "programme requires full-time commitment or leaving current employment"
        )
    for term in profile.ignore_terms or []:
        if term and re.search(rf"\b{re.escape(term.lower())}\b", text):
            hard_exclusions.append(f'owner ignore term matched: "{term}"')
    for pattern in SCAM_PATTERNS:
        if re.search(pattern, text):
            hard_exclusions.append("possible paid-to-apply or scam wording")
            break

    relevance, relevance_reason, role_family = _engineering_score(opportunity, profile)
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
            "role_family": role_family,
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
            if role_family in {"non_engineering", "non_target"}:
                reason += "; role title is outside backend engineering"
        elif role_family in {"non_engineering", "non_target"}:
            bucket = RecommendationBucket.archive
            reason = (
                "Role title is outside backend engineering; technical keyword matches in the "
                "body are not treated as engineering fit"
            )
        elif role_family in {"adjacent", "general_engineering"}:
            bucket = (
                RecommendationBucket.keep_on_radar
                if total >= 50
                else RecommendationBucket.archive
            )
            reason = (
                "Engineering role outside the target backend family; keep for monitoring only"
            )
        elif total >= 85:
            bucket = RecommendationBucket.act_now
            reason = "Verified eligibility and high deterministic score"
            if (
                profile.employment_stage == EmploymentStage.prejoin
                and opportunity.opportunity_type == OpportunityType.job
                and opportunity.employment_type
                and "full" in (opportunity.employment_type or "").lower()
            ):
                bucket = RecommendationBucket.prepare_early
                reason = (
                    "Strong fit, but this is a full-time role and the owner has a "
                    "committed employment start; prepare and revisit after gaining experience"
                )
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
