from __future__ import annotations

import json

from app.collectors.base import (
    SourceAdapter,
    conditional_headers,
    fetch_result_from_response,
)
from app.collectors.http import SafeFetcher
from app.db.models.enums import OpportunityType
from app.schemas.collector import (
    CompensationDTO,
    FetchResult,
    NormalizedCandidate,
    SourceConfig,
)
from app.services.eligibility import infer_country_codes, infer_remote_countries
from app.services.text import excerpt, html_to_text
from app.services.time import parse_datetime
from app.services.urls import canonicalize_url, domain_of


class AshbyAdapter(SourceAdapter):
    kind = "ats_ashby"
    supports_closure = True

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        base = source.config_json.get("base_url", "https://api.ashbyhq.com")
        return {domain_of(base) or "api.ashbyhq.com"}

    def request_url(self, source: SourceConfig) -> str:
        board = source.config_json.get("board_name")
        if not board:
            raise ValueError("Ashby source requires config.board_name")
        base = source.config_json.get("base_url", "https://api.ashbyhq.com").rstrip("/")
        return f"{base}/posting-api/job-board/{board}?includeCompensation=true"

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        url = self.request_url(source)
        response = await fetcher.get(url, headers=conditional_headers(source))
        content_json = None
        if response.content and response.status_code == 200:
            try:
                content_json = json.loads(response.content)
            except ValueError:
                content_json = None
        return fetch_result_from_response(
            source,
            response,
            content_json=content_json,
            scan_complete=True,
            source_url=url,
        )

    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        payload = result.content_json or {}
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("Ashby response is missing jobs[]")
        organization = source.config_json.get("organization_name") or source.name
        candidates: list[NormalizedCandidate] = []
        for job in jobs:
            if not isinstance(job, dict) or job.get("id") is None:
                continue
            external_id = str(job["id"])
            location = str(job.get("location") or "").strip()
            secondary = job.get("secondaryLocations") or []
            secondary_text = ", ".join(
                str(item.get("location"))
                for item in secondary
                if isinstance(item, dict) and item.get("location")
            )
            full_location = ", ".join(filter(None, [location, secondary_text]))
            description = html_to_text(
                job.get("descriptionPlain") or job.get("descriptionHtml") or ""
            )
            compensation = job.get("compensation") or {}
            summary = None
            if isinstance(compensation, dict):
                summary = compensation.get("compensationTierSummary") or compensation.get("summary")
            official_url = job.get("jobUrl") or job.get("applyUrl")
            if not official_url:
                continue
            is_remote = bool(job.get("isRemote")) or "remote" in full_location.lower()
            candidate = NormalizedCandidate(
                source_external_id=external_id,
                provider_key=f"ashby:{external_id}",
                title=str(job.get("title") or "Untitled role").strip(),
                organization_name=organization,
                organization_domain=source.config_json.get("organization_domain"),
                opportunity_type=OpportunityType.job,
                description_summary=excerpt(description, 1200),
                requirements_summary=excerpt(description, 2000),
                scope=str(job.get("department") or job.get("team") or "") or None,
                skills=[str(item) for item in job.get("skills") or [] if item],
                official_url=canonicalize_url(official_url),
                application_url=canonicalize_url(job.get("applyUrl") or official_url),
                location_text=full_location,
                is_remote=is_remote,
                workplace_type="remote" if is_remote else "onsite",
                employment_type=job.get("employmentType"),
                compensation=CompensationDTO(
                    raw=str(compensation) if compensation else None,
                    summary=str(summary) if summary else None,
                    cash=str(summary) if summary else None,
                ),
                published_at=parse_datetime(job.get("publishedAt")),
                source_payload={
                    "id": external_id,
                    "isRemote": job.get("isRemote"),
                    "location": job.get("location"),
                    "department": job.get("department"),
                    "team": job.get("team"),
                },
                evidence_excerpt=excerpt(description, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidates.append(candidate)
        return candidates
