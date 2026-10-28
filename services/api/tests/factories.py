from __future__ import annotations

import hashlib
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import SourceAdapter
from app.db.models.enums import (
    ApprovalStatus,
    DeadlinePrecision,
    EligibilityStatus,
    HealthStatus,
    LegalReviewStatus,
    Officialness,
    OpportunityType,
    SourceKind,
)
from app.db.models.source import Source
from app.schemas.collector import (
    CompensationDTO,
    FetchResult,
    NormalizedCandidate,
    SourceConfig,
)
from app.services.time import now_utc


async def make_source(
    session: AsyncSession,
    *,
    name: str = "Example ATS",
    kind: SourceKind = SourceKind.ats_greenhouse,
    url: str = "https://boards-api.greenhouse.io/v1/boards/example/jobs",
    config: dict | None = None,
    official: bool = True,
) -> Source:
    source = Source(
        name=name,
        source_kind=kind,
        root_url=url,
        config_json=config
        or {
            "board_token": "example",
            "organization_name": "Example",
            "organization_domain": "example.com",
        },
        officialness=Officialness.official if official else Officialness.credible_aggregator,
        enabled=True,
        approval_status=ApprovalStatus.approved,
        legal_review_status=LegalReviewStatus.approved,
        next_due_at=now_utc(),
        health_status=HealthStatus.healthy,
    )
    session.add(source)
    await session.flush()
    return source


def make_candidate(
    *,
    external_id: str = "1",
    title: str = "Senior Backend Engineer",
    description: str = (
        "Open to working professionals. Build distributed systems, cloud platform and "
        "PostgreSQL services. Compensation USD 120,000 per year."
    ),
    location: str = "Bengaluru, India",
    deadline_on: date | None = None,
    deadline_at: datetime | None = None,
    deadline_precision: DeadlinePrecision = DeadlinePrecision.unknown,
    deadline_timezone: str | None = None,
) -> NormalizedCandidate:
    return NormalizedCandidate(
        source_external_id=external_id,
        provider_key=f"fake:{external_id}",
        title=title,
        organization_name="Example",
        organization_domain="example.com",
        opportunity_type=OpportunityType.job,
        description_summary=description,
        requirements_summary=description,
        official_url=f"https://example.com/jobs/{external_id}",
        application_url=f"https://example.com/jobs/{external_id}/apply",
        location_text=location,
        workplace_type="remote" if "remote" in location.lower() else "onsite",
        is_remote="remote" in location.lower(),
        compensation=CompensationDTO(
            cash="USD 120,000 per year",
            currency="USD",
            period="per year",
            summary="USD 120,000 per year",
        ),
        country_codes=[],
        evidence_excerpt=description[:600],
        deadline_on=deadline_on,
        deadline_at=deadline_at,
        deadline_timezone=deadline_timezone,
        deadline_precision=deadline_precision,
    )


class FakeAdapter(SourceAdapter):
    kind = "ats_greenhouse"
    supports_closure = True

    def __init__(self, candidates: list[NormalizedCandidate]) -> None:
        self.candidates = candidates
        self.mode = "ok"
        self.scan_complete = True
        self.fetch_error: str | None = None

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        return {"boards-api.greenhouse.io"}

    async def fetch(self, source: SourceConfig, fetcher, cursor: str | None = None) -> FetchResult:
        if self.mode == "raise":
            raise RuntimeError("simulated collector failure")
        return FetchResult(
            source_id=source.id,
            fetched_at=now_utc(),
            http_status=200 if self.mode == "ok" else 503,
            content_type="application/json",
            raw_hash=hashlib.sha256(b"fixture").hexdigest(),
            raw_bytes=b"{}",
            scan_complete=self.scan_complete and self.mode == "ok",
            not_modified=False,
            error_class=self.fetch_error if self.mode != "ok" else None,
            error_message="source unavailable" if self.mode != "ok" else None,
            source_url=source.root_url,
        )

    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        if self.mode == "parse_error":
            raise ValueError("invalid source payload")
        return list(self.candidates)


def expected_eligibility() -> dict[str, EligibilityStatus]:
    return {
        "professional": EligibilityStatus.verified_yes,
        "india": EligibilityStatus.verified_yes,
    }
