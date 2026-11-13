import pytest

from app.db.models.enums import OpportunityType
from app.services.normalize import classify_opportunity, parse_compensation_text


def test_engineering_title_wins_over_founding_team_body() -> None:
    result = classify_opportunity(
        "Full-Stack Engineer (SDE-2) at Pinaca",
        "Seed-funded founding team in Gurugram.",
    )

    assert result == OpportunityType.job


def test_founding_engineer_title_is_a_job() -> None:
    result = classify_opportunity(
        "Founding Data Engineer (BigQuery, Python, SQL)",
        "Join a small founding team.",
    )

    assert result == OpportunityType.job


def test_intern_title_is_a_job() -> None:
    result = classify_opportunity(
        "AI Filmmaking Intern",
        "Join our founding team for a six-month internship.",
    )

    assert result == OpportunityType.job


def test_design_associate_title_wins_over_challenge_body() -> None:
    result = classify_opportunity(
        "Graphic Design Associate",
        "Take on a creative challenge with the design team.",
    )

    assert result == OpportunityType.job


def test_fellowship_title_wins_over_engineering_body() -> None:
    result = classify_opportunity(
        "Build for Bharat Fellow (AI, Engineering or Design)",
        "Work with government engineering teams.",
    )

    assert result == OpportunityType.fellowship


def test_compensation_ignores_full_job_description_without_pay_value() -> None:
    description = (
        "Company: Pinaca Location: Gurugram Type: Full Time "
        "Pinaca builds on-prem spatial AI with a 40-person team and $5M funding. "
        "The seat owns a self-hosted repository, backups and internal tools. "
        "Looking for 1-3 years of production code. Apply via careers.pinaca.org."
    )

    result = parse_compensation_text(description)

    assert result.cash is None
    assert result.summary is None
    assert result.raw is None


def test_compensation_extracts_explicit_lpa_range_only() -> None:
    description = (
        "Pinaca builds on-prem spatial AI. Compensation: INR 20-30 LPA + benefits. "
        "Full-time, onsite Gurugram. Process: warm-up call, technical round."
    )

    result = parse_compensation_text(description)

    assert result.cash == "INR 20-30 LPA"
    assert result.currency == "INR"
    assert result.period == "per year"
    assert result.summary == "Compensation: INR 20-30 LPA + benefits"


def test_compensation_extracts_explicit_stipend() -> None:
    description = (
        "Fellowship at a glance Duration: January-June 2027 Stipend: ₹40,000 per month "
        "Eligibility: Indian citizens graduating in 2027 or degree completed in 2024-2026"
    )

    result = parse_compensation_text(description)

    assert result.cash == "₹ 40,000"
    assert result.currency == "₹"
    assert result.period == "per month"
    assert result.summary == "Stipend: ₹40,000 per month"


def test_compensation_ignores_ad_spend_and_revenue_metrics() -> None:
    description = (
        "Monastic Media manages ₹40 Cr+ in ad spend and created ₹175 Cr+ in revenue. "
        "Stipend is discussed after the interview. Full-time, six-month internship."
    )

    result = parse_compensation_text(description)

    assert result.cash is None
    assert result.summary is None


def test_compensation_stops_at_benefit_list_without_punctuation() -> None:
    description = (
        "What you get: A paid internship, starting at ₹10,000 a month Direct access to the "
        "founders Hands-on work on a real production with the latest AI filmmaking tools"
    )

    result = parse_compensation_text(description)

    assert result.cash == "₹ 10,000"
    assert result.period == "per month"
    assert result.summary == "paid internship, starting at ₹10,000 a month"


def test_compensation_supports_lpa_without_currency_token() -> None:
    result = parse_compensation_text("Pay: 6-8 LPA Deadline: 10 September 2026")

    assert result.cash == "6-8 LPA"
    assert result.period == "per year"
    assert result.summary == "Pay: 6-8 LPA"


@pytest.mark.parametrize(
    ("title", "text", "expected"),
    [
        ("OSS Mentorship", "A full-time programme with mentors.", OpportunityType.mentorship),
        ("AI Fellowship", "Programme with mentor resources.", OpportunityType.fellowship),
        ("AI Residency", "Internship and fellowship resources.", OpportunityType.residency),
        ("Builder Programme", "Mentorship, fellowship and jobs.", OpportunityType.programme),
        ("Summer Internship", "Information for mentors.", OpportunityType.programme),
        ("Outreachy", "A full-time internship. Resources: Mentors", OpportunityType.programme),
        ("Community", "Information for mentors", OpportunityType.other),
        ("Backend Engineer", "Mentorship programme benefits", OpportunityType.job),
        ("Annual Hackathon", "A programme with mentors", OpportunityType.hackathon),
        ("Builder Challenge", "Mentorship programme", OpportunityType.competition),
        ("Research Grant", "Mentorship programme", OpportunityType.grant),
        ("Founder Accelerator", "Mentorship programme", OpportunityType.founder_programme),
    ],
)
def test_category_evidence_precedes_incidental_body_mentions(
    title: str, text: str, expected: OpportunityType
) -> None:
    assert classify_opportunity(title, text) == expected
