from __future__ import annotations

from datetime import UTC, date, datetime

from app.db.models.enums import DeadlinePrecision, EligibilityStatus
from app.schemas.collector import NormalizedCandidate
from app.services.eligibility import assess_eligibility
from app.services.time import extract_deadline_from_text, parse_deadline_text


def candidate(**overrides) -> NormalizedCandidate:
    values = {
        "source_external_id": "x",
        "title": "Platform Engineer",
        "organization_name": "Example",
        "official_url": "https://example.com/jobs/x",
        "description_summary": "Build backend systems.",
        "location_text": "Remote",
        "is_remote": True,
    }
    values.update(overrides)
    return NormalizedCandidate(**values)


def test_remote_alone_never_proves_india_eligibility() -> None:
    result = assess_eligibility(candidate(is_remote=True, location_text="Remote"))
    assert result.india_eligibility == EligibilityStatus.unknown


def test_explicit_india_location_is_verified() -> None:
    result = assess_eligibility(candidate(location_text="Bengaluru, India", is_remote=False))
    assert result.india_eligibility == EligibilityStatus.verified_yes


def test_remote_worldwide_is_verified_but_remote_us_is_not() -> None:
    worldwide = assess_eligibility(candidate(location_text="Remote - Worldwide"))
    us_only = assess_eligibility(candidate(location_text="Remote - United States"))
    assert worldwide.india_eligibility == EligibilityStatus.verified_yes
    assert us_only.india_eligibility == EligibilityStatus.verified_no


def test_india_mention_in_description_does_not_prove_location() -> None:
    result = assess_eligibility(
        candidate(
            location_text="Remote - United States",
            description_summary="Our largest office is in Bengaluru, India.",
        )
    )
    assert result.india_eligibility == EligibilityStatus.verified_no


def test_absence_of_student_restriction_is_unknown_not_yes() -> None:
    result = assess_eligibility(candidate(description_summary="Build distributed systems."))
    assert result.professional_eligibility == EligibilityStatus.unknown


def test_student_only_excludes_professionals() -> None:
    result = assess_eligibility(
        candidate(description_summary="Open only to current students graduating in 2027.")
    )
    assert result.professional_eligibility == EligibilityStatus.verified_no
    assert result.student_only is True


def test_date_only_deadline_keeps_cutoff_unknown() -> None:
    parsed = extract_deadline_from_text("Application deadline: 2026-11-15")
    assert parsed["deadline_on"] == date(2026, 11, 15)
    assert parsed["deadline_at"] is None
    assert parsed["deadline_precision"] == DeadlinePrecision.date_only


def test_exact_deadline_time_is_kept_with_timezone() -> None:
    parsed = extract_deadline_from_text("Applications close on 2026-11-15T23:59:00+05:30")
    assert parsed["deadline_at"] == datetime(2026, 11, 15, 18, 29, tzinfo=UTC)
    assert parsed["deadline_precision"] == DeadlinePrecision.exact


def test_random_date_is_not_treated_as_deadline() -> None:
    parsed = extract_deadline_from_text("Published 2026-11-15. Read our engineering blog.")
    assert parsed["deadline_precision"] == DeadlinePrecision.unknown
    assert parsed["deadline_on"] is None


def test_raw_parser_can_still_parse_explicitly_supplied_date() -> None:
    parsed = parse_deadline_text("15 November 2026")
    assert parsed["deadline_on"] == date(2026, 11, 15)
    assert parsed["deadline_at"] is None
