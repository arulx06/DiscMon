from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from app.api import routes
from app.collectors.http import FetchPolicy, validate_target
from app.collectors.static_html import StaticHTMLAdapter
from app.db.models.enums import DeadlinePrecision, EligibilityStatus, OpportunityType
from app.schemas.collector import FetchResult, SourceConfig
from app.services.discovery import _candidate_links
from app.services.eligibility import assess_eligibility
from app.services.time import now_utc
from tests.factories import make_source

FIXTURES = Path(__file__).parent / "fixtures" / "wikimedia_outreachy"
PROGRAMME_URL = "https://www.mediawiki.org/wiki/Outreachy"


async def test_wikimedia_directory_uses_only_canonical_programme_links(session) -> None:
    source = await make_source(
        session, kind="static_html", url="https://www.mediawiki.org/wiki/Outreach_programs",
        config={"discovery": {"link_selector": 'a[href="/wiki/Outreachy"]'}},
    )
    result = FetchResult(
        source_id=source.id, fetched_at=now_utc(), http_status=200,
        raw_bytes=(FIXTURES / "directory.html").read_bytes(),
    )
    # The real directory repeats canonical links, including a thumbnail-only anchor.
    links = _candidate_links(source, result)
    assert len(links) == 2
    assert set(links) == {PROGRAMME_URL}


def test_wikimedia_outreachy_preserves_full_time_constraint_and_field_origins() -> None:
    body = (FIXTURES / "programme.html").read_bytes()
    metadata = json.loads((FIXTURES / "capture.json").read_text())["pages"]["programme"]
    source = SourceConfig(
        id=uuid.uuid4(), name="Not the page title", source_kind="static_html",
        root_url=PROGRAMME_URL, officialness="official",
        config_json={"organization_name": "Wikimedia", "description_selector": ".mw-parser-output"},
    )
    result = FetchResult(
        source_id=source.id, fetched_at=now_utc(), http_status=200,
        content_type=metadata["headers"]["content-type"],
        last_modified=metadata["headers"]["last-modified"],
        raw_bytes=body, raw_hash=hashlib.sha256(body).hexdigest(), source_url=PROGRAMME_URL,
    )
    candidate, = StaticHTMLAdapter().parse(source, result)
    assert candidate.title == "Outreachy"
    assert candidate.organization_name == "Wikimedia"  # Explicit source configuration.
    assert candidate.organization_domain == "mediawiki.org"
    assert candidate.official_url == candidate.application_url == PROGRAMME_URL
    assert candidate.opportunity_type == OpportunityType.mentorship
    assert "full-time internship" in candidate.evidence_excerpt
    assert candidate.source_payload == {"page_hash": metadata["fixture_sha256"]}
    assert candidate.country_codes == candidate.allowed_remote_countries == []
    assert candidate.is_remote is False  # No remote configuration or claim inferred.
    assert candidate.compensation.cash is None
    assert candidate.deadline_on is candidate.deadline_at is candidate.deadline_timezone is None
    assert candidate.deadline_precision == DeadlinePrecision.unknown
    assert candidate.published_at is None  # HTTP Last-Modified is not a programme date.
    assert candidate.employment_conflict is True
    eligibility = assess_eligibility(candidate)
    assert eligibility.india_eligibility == EligibilityStatus.unknown
    assert eligibility.professional_eligibility == EligibilityStatus.unknown


async def test_wikimedia_www_host_survives_fetch_and_promotion_validation(monkeypatch) -> None:
    source = SourceConfig(
        id=uuid.uuid4(), name="Wikimedia", source_kind="static_html", root_url=PROGRAMME_URL,
    )
    hosts = StaticHTMLAdapter().allowed_hosts(source)
    assert hosts == {"www.mediawiki.org"}

    async def resolve_public(host, port):
        assert host == "www.mediawiki.org" and port == 443
        return ["208.80.154.224"]

    monkeypatch.setattr("app.collectors.http._resolve_host", resolve_public)
    await validate_target(PROGRAMME_URL, FetchPolicy(allowed_hosts=hosts))
    await routes._validate_source_root(PROGRAMME_URL)
