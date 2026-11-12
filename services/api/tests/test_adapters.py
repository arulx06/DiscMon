from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import pytest

from app.collectors.ashby import AshbyAdapter
from app.collectors.github import GitHubAdapter
from app.collectors.greenhouse import GreenhouseAdapter
from app.collectors.http import HttpResponse
from app.collectors.lever import LeverAdapter
from app.collectors.rss_atom import RSSAtomAdapter
from app.collectors.static_html import StaticHTMLAdapter
from app.db.models.enums import DeadlinePrecision, OpportunityType, SourceKind
from app.schemas.collector import FetchResult, SourceConfig
from app.services.time import now_utc

FIXTURES = Path(__file__).parent / "fixtures"


def _source(
    kind: SourceKind,
    *,
    root_url: str,
    config: dict | None = None,
) -> SourceConfig:
    return SourceConfig(
        id=uuid.uuid4(),
        name="Example Source",
        source_kind=kind,
        root_url=root_url,
        config_json=config or {},
    )


def _result(source: SourceConfig, **kwargs) -> FetchResult:
    return FetchResult(
        source_id=source.id,
        fetched_at=now_utc(),
        http_status=200,
        **kwargs,
    )


class StubFetcher:
    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.content_type = content_type

    async def get(self, url: str, headers: dict | None = None, conditional: bool = True):
        return HttpResponse(
            url=url,
            status_code=200,
            headers={"content-type": self.content_type},
            content=self.content,
            elapsed_ms=1,
        )


def test_greenhouse_fixture_parses_identity_and_eligibility_signals() -> None:
    source = _source(
        SourceKind.ats_greenhouse,
        root_url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        config={
            "board_token": "example",
            "organization_name": "Example",
            "organization_domain": "example.com",
        },
    )
    payload = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    result = _result(source, content_json=payload, scan_complete=True)

    candidates = GreenhouseAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_key == "greenhouse:101"
    assert candidate.title == "Senior Backend Engineer"
    assert candidate.organization_domain == "example.com"
    assert candidate.location_text == "Bengaluru, India"
    assert "IN" in candidate.country_codes
    assert candidate.compensation.raw == "USD 120000"
    assert candidate.employment_type == "Full-time"


def test_lever_fixture_parses_remote_india_and_salary() -> None:
    source = _source(
        SourceKind.ats_lever,
        root_url="https://api.lever.co/v0/postings/example",
        config={
            "site": "example",
            "organization_name": "Example",
            "organization_domain": "example.com",
        },
    )
    payload = json.loads((FIXTURES / "lever_postings.json").read_text(encoding="utf-8"))
    result = _result(source, content_json=payload, scan_complete=True)

    candidates = LeverAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_key == "lever:lever-abc"
    assert candidate.is_remote is True
    assert "IN" in candidate.country_codes
    assert "IN" in candidate.allowed_remote_countries
    assert candidate.compensation.currency == "USD"
    assert candidate.workplace_type == "remote"


def test_ashby_fixture_combines_secondary_locations() -> None:
    source = _source(
        SourceKind.ats_ashby,
        root_url="https://api.ashbyhq.com/posting-api/job-board/example",
        config={
            "board_name": "example",
            "organization_name": "Example",
            "organization_domain": "example.com",
        },
    )
    payload = json.loads((FIXTURES / "ashby_jobs.json").read_text(encoding="utf-8"))
    result = _result(source, content_json=payload, scan_complete=True)

    candidates = AshbyAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_key == "ashby:ashby-1"
    assert candidate.is_remote is True
    assert "India" in (candidate.location_text or "")
    assert "IN" in candidate.country_codes
    assert candidate.compensation.summary == "INR 40L - INR 60L"
    assert candidate.compensation.cash == "INR 40L - INR 60L"
    assert candidate.compensation.equity == "Offers Equity"
    assert candidate.compensation.currency == "INR"
    assert candidate.compensation.period == "per year"
    assert candidate.scope == "Engineering"


def test_rss_entry_uses_author_and_location_metadata() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://fossunited.org/jobs/rss.xml",
    )
    result = _result(
        source,
        content_json={
            "feed": {"title": "FOSS United Job Board"},
            "entries": [
                {
                    "id": "job-1",
                    "title": "Full-Stack Engineer (SDE-2) at Pinaca",
                    "link": "https://fossunited.org/jobs/job-1",
                    "author": "Pinaca",
                    "summary": (
                        "<p><strong>Company:</strong> Pinaca</p>"
                        "<p><strong>Location:</strong> Gurugram</p>"
                        "<p><strong>Type:</strong> Full Time</p>"
                        "<p>Looking for 4+ years in production.</p>"
                    ),
                }
            ],
        },
    )

    candidates = RSSAtomAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.organization_name == "Pinaca"
    assert candidate.organization_domain is None
    assert candidate.location_text == "Gurugram"
    assert candidate.employment_type == "FullTime"
    assert candidate.workplace_type == "unknown"
    assert "IN" in candidate.country_codes
    assert candidate.is_remote is False
    assert candidate.compensation.cash is None
    assert candidate.compensation.summary is None
    assert candidate.compensation.raw is None


def test_rss_entry_extracts_only_explicit_compensation_snippet() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://fossunited.org/jobs/rss.xml",
    )
    result = _result(
        source,
        content_json={
            "feed": {"title": "FOSS United Job Board"},
            "entries": [
                {
                    "id": "job-2",
                    "title": "Full-Stack Engineer (SDE-1) at Pinaca",
                    "link": "https://fossunited.org/jobs/job-2",
                    "author": "Pinaca",
                    "summary": (
                        "<p>Pinaca builds on-prem spatial AI with $5M funding.</p>"
                        "<p>Location: Hybrid Type: Full Time</p>"
                        "<p>Compensation: INR 20-30 LPA + benefits.</p>"
                        "<p>Full-time, onsite Gurugram.</p>"
                    ),
                }
            ],
        },
    )

    candidate = RSSAtomAdapter().parse(source, result)[0]

    assert candidate.workplace_type == "hybrid"
    assert candidate.employment_type == "FullTime"
    assert candidate.compensation.cash == "INR 20-30 LPA"
    assert candidate.compensation.period == "per year"
    assert candidate.compensation.summary == "Compensation: INR 20-30 LPA + benefits"
    assert "$5M funding" not in (candidate.compensation.summary or "")


def test_rss_yearless_deadline_is_anchored_to_publication_date() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://fossunited.org/jobs/rss.xml",
    )
    result = _result(
        source,
        content_json={
            "feed": {"title": "FOSS United Job Board"},
            "entries": [
                {
                    "id": "job-3",
                    "title": "Graphic Design Associate at FOSS United",
                    "link": "https://fossunited.org/jobs/job-3",
                    "published_parsed": [2026, 8, 3, 0, 0, 0, 0, 0, 0],
                    "summary": "<p>Applications close 10 September 11:59pm.</p>",
                }
            ],
        },
    )

    candidate = RSSAtomAdapter().parse(source, result)[0]

    assert candidate.deadline_on == date(2026, 9, 10)
    assert candidate.deadline_at is None
    assert candidate.deadline_precision == DeadlinePrecision.date_only


def test_atom_entry_uses_company_link_and_location_tag() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://hasjob.co/feed",
    )
    result = _result(
        source,
        content_json={
            "feed": {"title": "All jobs - Hasjob"},
            "entries": [
                {
                    "id": "https://hasjob.co/example.com/abc",
                    "title": "Backend Engineer at Example Labs, building developer tools",
                    "link": "https://hasjob.co/example.com/abc",
                    "location": "Bangalore",
                    "summary": (
                        '<p><strong><a href="https://example.com">Example Labs</a></strong><br />'
                        "Bangalore</p><p>Build reliable backend systems.</p>"
                    ),
                }
            ],
        },
    )

    candidates = RSSAtomAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.organization_name == "Example Labs"
    assert candidate.organization_domain == "example.com"
    assert candidate.location_text == "Bangalore"
    assert "IN" in candidate.country_codes


def test_atom_entry_extracts_explicit_stipend_not_programme_description() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://hasjob.co/feed",
    )
    result = _result(
        source,
        content_json={
            "feed": {"title": "All jobs - Hasjob"},
            "entries": [
                {
                    "id": "https://hasjob.co/bharatdigital.io/neqif",
                    "title": "Build for Bharat Fellow (AI/Engineering/Design)",
                    "link": "https://hasjob.co/bharatdigital.io/neqif",
                    "summary": (
                        "<p>Bharat Digital Anywhere The Build for Bharat Fellowship is a "
                        "paid, six-month programme.</p>"
                        "<p>Duration: January-June 2027 Stipend: ₹40,000 per month</p>"
                        "<p>Eligibility: Indian citizens graduating in 2027 or who completed "
                        "their latest degree in 2024-2026.</p>"
                    ),
                }
            ],
        },
    )

    candidate = RSSAtomAdapter().parse(source, result)[0]

    assert candidate.compensation.cash == "₹ 40,000"
    assert candidate.compensation.period == "per month"
    assert candidate.compensation.summary == "Stipend: ₹40,000 per month"
    assert "six-month programme" not in (candidate.compensation.summary or "")


async def test_rss_fixture_is_fetched_and_parsed_with_deadline() -> None:
    source = _source(
        SourceKind.rss,
        root_url="https://example.org/opportunities/feed.xml",
        config={"organization_name": "Example Opportunities"},
    )
    adapter = RSSAtomAdapter()
    fetcher = StubFetcher(
        (FIXTURES / "rss_feed.xml").read_bytes(),
        "application/rss+xml",
    )

    result = await adapter.fetch(source, fetcher)
    candidates = adapter.parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "AI Residency 2027"
    assert candidate.opportunity_type == OpportunityType.residency
    assert candidate.deadline_on == date(2026, 11, 15)
    assert candidate.deadline_at is None
    assert candidate.is_remote is True
    assert candidate.allowed_remote_countries == []
    assert candidate.country_codes == []


def test_github_fixture_uses_repository_owner_and_material_link() -> None:
    source = _source(
        SourceKind.github,
        root_url="https://api.github.com/repos/example/project/releases",
        config={"repos": ["example/project"], "mode": "releases"},
    )
    payload = json.loads((FIXTURES / "github_releases.json").read_text(encoding="utf-8"))
    result = _result(source, content_json=payload)

    candidates = GitHubAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.organization_name == "example"
    assert candidate.provider_key == "github:example/project:releases:99"
    assert candidate.opportunity_type == OpportunityType.fellowship
    assert candidate.deadline_on == date(2026, 11, 30)
    assert candidate.deadline_at is None


def test_static_html_fixture_uses_configured_selectors() -> None:
    source = _source(
        SourceKind.static_html,
        root_url="https://example.org/residency",
        config={
            "organization_name": "Example",
            "description_selector": "main",
            "remote": True,
        },
    )
    raw = (FIXTURES / "static_page.html").read_bytes()
    result = _result(source, raw_bytes=raw, raw_hash="fixture-hash")

    candidates = StaticHTMLAdapter().parse(source, result)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Global AI Residency 2027"
    assert candidate.opportunity_type == OpportunityType.residency
    assert candidate.deadline_on == date(2026, 11, 15)
    assert candidate.deadline_at is None
    assert candidate.is_remote is True


def test_invalid_greenhouse_payload_is_rejected() -> None:
    source = _source(
        SourceKind.ats_greenhouse,
        root_url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        config={"board_token": "example"},
    )
    result = _result(source, content_json={})

    with pytest.raises(ValueError, match="jobs"):
        GreenhouseAdapter().parse(source, result)
