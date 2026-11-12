from __future__ import annotations

import pytest

from app.db.models.enums import (
    CredibilityLevel,
    EligibilityStatus,
    LifeState,
    OpportunityType,
    RecommendationBucket,
)
from app.db.models.opportunity import Opportunity
from app.db.models.user import UserProfile
from app.services.scoring import assess


def _profile() -> UserProfile:
    return UserProfile(
        employment_stage="prejoin",
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


def _employed_profile() -> UserProfile:
    return UserProfile(
        employment_stage="employed",
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


def _opportunity(
    *,
    title: str,
    description: str,
    professional: EligibilityStatus = EligibilityStatus.verified_yes,
    india: EligibilityStatus = EligibilityStatus.verified_yes,
) -> Opportunity:
    return Opportunity(
        title=title,
        opportunity_type=OpportunityType.job,
        description_summary=description,
        requirements_summary=description,
        location_text="Bengaluru, India",
        employment_type="full-time",
        scope="Engineering",
        professional_eligibility=professional,
        india_eligibility=india,
        student_only=False,
        credibility_level=CredibilityLevel.high,
        monetary_value_json={"cash": "INR 40L"},
        requires_relocation=False,
        deadline_on=None,
        deadline_at=None,
    )


def test_backend_engineer_receives_high_engineering_fit() -> None:
    opportunity = _opportunity(
        title="Senior Backend Engineer",
        description=(
            "Build distributed systems, cloud infrastructure and PostgreSQL services "
            "with Python and open source developer tools."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "target"
    assert engineering["score"] == 25
    assert result.score_total >= 85
    # Prejoin user: full-time job is capped at prepare_early to avoid
    # encouraging abandoning the committed employment start
    assert result.recommended_bucket == RecommendationBucket.prepare_early


def test_employed_user_receives_act_now_for_high_scoring_role() -> None:
    opportunity = _opportunity(
        title="Senior Backend Engineer",
        description=(
            "Build distributed systems, cloud infrastructure and PostgreSQL services "
            "with Python and open source developer tools."
        ),
    )

    result = assess(opportunity, _employed_profile())

    assert result.score_total >= 85
    assert result.recommended_bucket == RecommendationBucket.act_now


def test_prejoin_non_fulltime_opportunity_can_reach_act_now() -> None:
    """Programmes and fellowships are not subject to the prejoin full-time cap."""
    opportunity = Opportunity(
        title="Backend Security Engineer Fellowship",
        opportunity_type=OpportunityType.fellowship,
        description_summary=(
            "Work on backend, distributed systems, cloud infrastructure, platform security "
            "and PostgreSQL open source developer tools."
        ),
        requirements_summary="Strong background in backend and security engineering.",
        location_text="Remote — India",
        employment_type=None,
        scope="Engineering",
        professional_eligibility=EligibilityStatus.verified_yes,
        india_eligibility=EligibilityStatus.verified_yes,
        student_only=False,
        credibility_level=CredibilityLevel.high,
        monetary_value_json={"cash": "USD 50000"},
        requires_relocation=False,
        deadline_on=None,
        deadline_at=None,
    )

    result = assess(opportunity, _profile())

    # Fellowship with an engineering title is NOT subject to the prejoin
    # full-time job cap, so it CAN reach act_now
    assert result.score_total >= 85
    assert result.recommended_bucket == RecommendationBucket.act_now


@pytest.mark.parametrize(
    ("title", "expected_hit"),
    [
        ("Communications Lead, Cyber", "communications"),
        ("Product Marketing Lead, API Models", "marketing"),
        ("Product Designer, Engineering Acceleration", "designer"),
    ],
)
def test_technical_body_words_do_not_make_non_engineering_titles_relevant(
    title: str, expected_hit: str
) -> None:
    opportunity = _opportunity(
        title=title,
        description=(
            "Work with distributed systems, cloud infrastructure, platform security, "
            "PostgreSQL, open source developer tools and machine learning teams."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "non_engineering"
    assert expected_hit in engineering["reason"]
    assert engineering["score"] <= 4
    assert result.recommended_bucket == RecommendationBucket.archive
    assert "outside backend engineering" in result.recommendation_reason


def test_non_engineering_role_with_unknown_eligibility_stays_in_verification() -> None:
    opportunity = _opportunity(
        title="Growth Marketing Manager, SMB Ads",
        description="Partner with platform and security teams on cloud infrastructure launches.",
        professional=EligibilityStatus.unknown,
        india=EligibilityStatus.unknown,
    )

    result = assess(opportunity, _profile())

    assert result.factors["engineering_relevance"]["role_family"] == "non_engineering"
    assert result.recommended_bucket == RecommendationBucket.needs_verification
    assert "outside backend engineering" in result.recommendation_reason


def test_adjacent_engineering_manager_is_not_promoted_to_apply_now() -> None:
    opportunity = _opportunity(
        title="Engineering Manager, Core Services",
        description=(
            "Lead distributed systems, cloud infrastructure, platform reliability and "
            "security engineering teams using PostgreSQL and Python."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "adjacent"
    assert engineering["score"] <= 14
    assert result.recommended_bucket == RecommendationBucket.keep_on_radar


def test_non_engineering_title_is_not_promoted_to_apply_now() -> None:
    opportunity = _opportunity(
        title="Account Director, Cyber",
        description=(
            "Sell cloud infrastructure, platform security and PostgreSQL services to "
            "distributed systems teams."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "non_engineering"
    assert engineering["score"] <= 4
    assert result.recommended_bucket == RecommendationBucket.archive


def test_general_engineering_title_is_capped_below_apply_now() -> None:
    opportunity = _opportunity(
        title="Android Engineer, Ad Formats",
        description=(
            "Build mobile clients for distributed systems, cloud infrastructure, platform "
            "security and PostgreSQL services."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "general_engineering"
    assert engineering["score"] <= 16
    assert result.recommended_bucket == RecommendationBucket.keep_on_radar


def test_title_without_engineering_function_is_archived() -> None:
    opportunity = _opportunity(
        title="AI Transformation Owner, CRO",
        description=(
            "Partner with cloud infrastructure, platform security and distributed systems "
            "engineering teams."
        ),
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "non_target"
    assert engineering["score"] <= 4
    assert result.recommended_bucket == RecommendationBucket.archive


def test_professional_and_india_eligibility_remain_independent_gates() -> None:
    professional_no = assess(
        _opportunity(
            title="Senior Backend Engineer",
            description="Build distributed systems and cloud infrastructure.",
            professional=EligibilityStatus.verified_no,
        ),
        _profile(),
    )
    india_no = assess(
        _opportunity(
            title="Senior Backend Engineer",
            description="Build distributed systems and cloud infrastructure.",
            india=EligibilityStatus.verified_no,
        ),
        _profile(),
    )

    assert professional_no.recommended_bucket == RecommendationBucket.excluded
    assert professional_no.factors["professional_eligibility"]["score"] == 0
    assert professional_no.factors["location_feasibility"]["score"] == 15
    assert india_no.recommended_bucket == RecommendationBucket.excluded
    assert india_no.factors["professional_eligibility"]["score"] == 20
    assert india_no.factors["location_feasibility"]["score"] == 0



def test_closed_opportunity_is_excluded() -> None:
    """Closed opportunities are excluded via hard gate, regardless of scoring."""
    opportunity = _opportunity(
        title="Senior Backend Engineer",
        description="Build distributed systems and cloud infrastructure.",
    )
    opportunity.life_state = LifeState.closed

    result = assess(opportunity, _profile())

    assert result.hard_gate_status.value == "excluded"
    assert result.recommended_bucket == RecommendationBucket.excluded
    assert "closed" in result.recommendation_reason


def test_archived_opportunity_is_excluded() -> None:
    opportunity = _opportunity(
        title="Senior Backend Engineer",
        description="Build distributed systems and cloud infrastructure.",
    )
    opportunity.life_state = LifeState.archived

    result = assess(opportunity, _profile())

    assert result.hard_gate_status.value == "excluded"
    assert result.recommended_bucket == RecommendationBucket.excluded
    assert "archived" in result.recommendation_reason


def test_employment_conflict_is_excluded() -> None:
    """Programmes requiring full-time commitment that conflicts with employment."""
    opportunity = Opportunity(
        title="Open Source Residency",
        opportunity_type=OpportunityType.residency,
        description_summary="Work on open-source infrastructure full time.",
        requirements_summary="Must be available full time.",
        location_text="Remote",
        employment_type=None,
        scope="Engineering",
        professional_eligibility=EligibilityStatus.verified_yes,
        india_eligibility=EligibilityStatus.verified_yes,
        student_only=False,
        credibility_level=CredibilityLevel.high,
        monetary_value_json={"cash": "USD 50000"},
        requires_relocation=False,
        employment_conflict=True,
        deadline_on=None,
        deadline_at=None,
    )

    result = assess(opportunity, _profile())

    assert result.hard_gate_status.value == "excluded"
    assert result.recommended_bucket == RecommendationBucket.excluded
    assert "full-time commitment" in result.recommendation_reason


def test_build_for_bharat_closed_is_excluded() -> None:
    """Build for Bharat is closed; it should be excluded, not needs_verification."""
    opportunity = Opportunity(
        title="Build for Bharat Fellow (AI, Engineering or Design)",
        opportunity_type=OpportunityType.fellowship,
        description_summary="A fellowship programme for builders in India.",
        requirements_summary=None,
        location_text="India",
        employment_type=None,
        scope=None,
        professional_eligibility=EligibilityStatus.unknown,
        india_eligibility=EligibilityStatus.verified_yes,
        student_only=False,
        credibility_level=CredibilityLevel.medium,
        monetary_value_json={},
        requires_relocation=False,
        deadline_on=None,
        deadline_at=None,
    )
    opportunity.life_state = LifeState.closed

    result = assess(opportunity, _profile())

    assert result.recommended_bucket == RecommendationBucket.excluded
    assert "closed" in result.recommendation_reason


def test_upside_reason_varies_by_opportunity_type() -> None:
    """Each opportunity type gets a descriptive reason, not a generic one."""
    job = _opportunity(
        title="Backend Engineer",
        description="Cloud infrastructure engineering.",
    )
    fellowship = Opportunity(
        title="Engineering Fellowship",
        opportunity_type=OpportunityType.fellowship,
        description_summary="A fellowship for engineers.",
        requirements_summary=None,
        location_text="Remote",
        employment_type=None,
        scope="Engineering",
        professional_eligibility=EligibilityStatus.verified_yes,
        india_eligibility=EligibilityStatus.verified_yes,
        student_only=False,
        credibility_level=CredibilityLevel.medium,
        monetary_value_json={},
        requires_relocation=False,
        deadline_on=None,
        deadline_at=None,
    )

    job_result = assess(job, _profile())
    fellowship_result = assess(fellowship, _profile())

    job_upside = job_result.factors["career_upside"]["reason"]
    fellowship_upside = fellowship_result.factors["career_upside"]["reason"]
    assert "job opening" in job_upside
    assert "fellowship" in fellowship_upside
    assert job_upside != fellowship_upside
    # The old static "Rare programme type" string should not appear
    assert "Rare programme type" not in job_upside
    assert "Rare programme type" not in fellowship_upside


def test_technical_mentorship_programme_gets_engineering_relevance() -> None:
    """Non-job technical programmes (fellowships/mentorships) with project titles

    are recognized by technical body evidence rather than rejected as non_target.
    """
    opportunity = Opportunity(
        title="[CNCF LFX Proposal] Jaeger OpenTelemetry-Native Query and State Layers",
        opportunity_type=OpportunityType.mentorship,
        description_summary=(
            "Work on distributed tracing systems, backend query architecture, "
            "cloud infrastructure, database storage layers, and open source developer tools."
        ),
        requirements_summary=(
            "Experience with distributed systems, backend services, and Go or Python."
        ),
        location_text="Remote — Worldwide",
        employment_type=None,
        scope="Open Source",
        professional_eligibility=EligibilityStatus.verified_yes,
        india_eligibility=EligibilityStatus.verified_yes,
        student_only=False,
        credibility_level=CredibilityLevel.high,
        monetary_value_json={"cash": "USD 3000", "summary": "Stipend: $3000"},
        requires_relocation=False,
        deadline_on=None,
        deadline_at=None,
        life_state=LifeState.open,
    )

    result = assess(opportunity, _profile())

    engineering = result.factors["engineering_relevance"]
    assert engineering["role_family"] == "target"
    assert engineering["score"] >= 20
    assert result.score_total >= 80
    # Because it is a mentorship (not a full-time job), prejoin user is not capped:
    assert result.recommended_bucket in (
        RecommendationBucket.act_now,
        RecommendationBucket.prepare_early,
    )


def test_open_opportunity_not_excluded_by_life_state() -> None:
    """Open opportunities should pass the life_state check."""
    opportunity = _opportunity(
        title="Backend Engineer",
        description="Cloud infrastructure engineering.",
    )
    opportunity.life_state = LifeState.open

    result = assess(opportunity, _profile())

    assert result.recommended_bucket != RecommendationBucket.excluded
