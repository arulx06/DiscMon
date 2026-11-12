from __future__ import annotations

from app.db.models.enums import (
    CredibilityLevel,
    EligibilityStatus,
    HardGateStatus,
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


def _make_opp(
    *,
    title: str,
    opportunity_type: OpportunityType = OpportunityType.job,
    description: str = "",
    requirements: str = "",
    location: str = "Bengaluru, India",
    professional: EligibilityStatus = EligibilityStatus.verified_yes,
    india: EligibilityStatus = EligibilityStatus.verified_yes,
    life_state: LifeState = LifeState.new,
    credibility: CredibilityLevel = CredibilityLevel.medium,
    monetary_value: dict | None = None,
    student_only: bool = False,
    scope: str | None = None,
    employment_type: str | None = "full-time",
    employment_conflict: bool = False,
) -> Opportunity:
    return Opportunity(
        title=title,
        opportunity_type=opportunity_type,
        description_summary=description or title,
        requirements_summary=requirements or description,
        location_text=location,
        scope=scope,
        employment_type=employment_type,
        professional_eligibility=professional,
        india_eligibility=india,
        student_only=student_only,
        credibility_level=credibility,
        monetary_value_json=monetary_value or {},
        life_state=life_state,
        employment_conflict=employment_conflict,
    )


class TestIDFCScoringAudit:
    """Scoring audit for the IDFC prejoin profile."""

    def test_pinaca_sde1_prejoin_prepare_early(self) -> None:
        opp = _make_opp(
            title="Backend Software Engineer (SDE-1)",
            description="Software Development Engineer at Pinaca Labs Gurugram.",
            requirements=(
                "Build backend services with distributed systems, cloud infrastructure "
                "and PostgreSQL open source tools."
            ),
            location="Gurugram, India",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "INR 20-30 LPA"},
        )
        result = assess(opp, _profile())
        assert result.factors["engineering_relevance"]["role_family"] == "target"
        assert result.recommended_bucket == RecommendationBucket.prepare_early
        assert result.score_total >= 80

    def test_pinaca_sde2_prejoin_prepare_early(self) -> None:
        opp = _make_opp(
            title="Backend Software Engineer (SDE-2)",
            description="Software Development Engineer II at Pinaca Labs.",
            requirements=(
                "Build distributed systems, cloud platform and PostgreSQL services."
            ),
            location="Gurugram, India",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "INR 25-35 LPA"},
        )
        result = assess(opp, _profile())
        assert result.factors["engineering_relevance"]["role_family"] == "target"
        assert result.recommended_bucket == RecommendationBucket.prepare_early

    def test_openai_communications_lead_not_act_now(self) -> None:
        opp = _make_opp(
            title="Communications Lead, Cyber",
            description=(
                "Lead cybersecurity communications and strategy; partner with "
                "distributed systems and security engineering teams."
            ),
            professional=EligibilityStatus.unknown,
            credibility=CredibilityLevel.high,
        )
        result = assess(opp, _profile())
        assert result.recommended_bucket == RecommendationBucket.needs_verification
        assert result.factors["engineering_relevance"]["role_family"] == "non_engineering"

    def test_student_only_internship_excluded(self) -> None:
        opp = _make_opp(
            title="Backend Intern",
            description="Open to current students graduating in 2027.",
            requirements="Currently enrolled in a BTech program.",
            location="Bangalore, India",
            student_only=True,
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "INR 15,000 per month"},
        )
        result = assess(opp, _profile())
        assert result.hard_gate_status == HardGateStatus.excluded
        assert result.recommended_bucket == RecommendationBucket.excluded
        assert "student" in result.recommendation_reason

    def test_expired_build_for_bharat_excluded(self) -> None:
        opp = _make_opp(
            title="Build for Bharat Fellow",
            opportunity_type=OpportunityType.fellowship,
            description="A fellowship programme for builders in India.",
            location="India",
            employment_type=None,
            professional=EligibilityStatus.unknown,
            life_state=LifeState.closed,
        )
        result = assess(opp, _profile())
        assert result.recommended_bucket == RecommendationBucket.excluded
        assert "closed" in result.recommendation_reason

    def test_india_unknown_remote_role_needs_verification(self) -> None:
        opp = _make_opp(
            title="Remote DevOps Engineer",
            description="Full-time remote DevOps engineer.",
            location="Remote - United States",
            india=EligibilityStatus.unknown,
        )
        result = assess(opp, _profile())
        assert result.recommended_bucket == RecommendationBucket.needs_verification
        assert result.factors["professional_eligibility"]["score"] == 20
        assert "never inferred" in result.factors["location_feasibility"]["reason"]

    def test_genuine_oss_mentorship_target_role(self) -> None:
        opp = _make_opp(
            title="[CNCF LFX Proposal] Jaeger Distributed Tracing",
            opportunity_type=OpportunityType.mentorship,
            description=(
                "Work on distributed tracing systems, backend query architecture, "
                "database storage layers, and open source developer tools."
            ),
            requirements="Experience with distributed systems, Go or Python.",
            location="Remote — Worldwide",
            employment_type=None,
            scope="Open Source",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "USD 3000", "summary": "Stipend: $3000"},
        )
        result = assess(opp, _profile())
        assert result.factors["engineering_relevance"]["role_family"] == "target"
        assert result.factors["engineering_relevance"]["score"] >= 20
        assert result.recommended_bucket in (
            RecommendationBucket.act_now,
            RecommendationBucket.prepare_early,
        )

    def test_future_role_requires_experience_prepare_early(self) -> None:
        opp = _make_opp(
            title="Senior Backend Engineer (1+ years experience)",
            description=(
                "Architect and build cloud infrastructure, distributed systems "
                "and PostgreSQL services."
            ),
            requirements="1-3 years of production experience required.",
            location="Hybrid — Remote — India",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "USD 180,000 per year"},
        )
        result = assess(opp, _profile())
        assert result.recommended_bucket == RecommendationBucket.prepare_early

    def test_employment_conflict_is_hard_excluded(self) -> None:
        opp = _make_opp(
            title="Software Engineer (Full Time)",
            description="Full-time software engineer at a tech company.",
            requirements="Strong backend engineering background.",
            location="Bangalore, India",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "USD 400,000 per year"},
            employment_conflict=True,
        )
        result = assess(opp, _profile())
        assert result.hard_gate_status == HardGateStatus.excluded
        assert result.recommended_bucket == RecommendationBucket.excluded
        assert "full-time commitment" in result.recommendation_reason

    def test_fellowship_reaches_act_now_for_prejoin(self) -> None:
        opp = _make_opp(
            title="Cloud Infrastructure Research Fellowship",
            opportunity_type=OpportunityType.fellowship,
            description="Research and build cloud infrastructure, distributed systems.",
            requirements="Candidates should have experience with Go and Kubernetes.",
            location="Remote — Worldwide",
            employment_type=None,
            scope="Research",
            credibility=CredibilityLevel.high,
            monetary_value={"cash": "USD 50,000 per year"},
        )
        result = assess(opp, _profile())
        assert result.recommended_bucket == RecommendationBucket.act_now

    def test_upside_reason_varies_by_type(self) -> None:
        job_upside = assess(
            _make_opp(
                title="Backend Engineer",
                description="Build cloud infrastructure backend.",
                credibility=CredibilityLevel.high,
                monetary_value={"cash": "USD 150,000"},
            ),
            _profile(),
        ).factors["career_upside"]["reason"]
        fellowship_upside = assess(
            _make_opp(
                title="Infrastructure Fellow",
                opportunity_type=OpportunityType.fellowship,
                description="Research and build cloud infrastructure.",
            ),
            _profile(),
        ).factors["career_upside"]["reason"]
        assert "job opening" in job_upside.lower()
        assert "fellowship" in fellowship_upside.lower()
