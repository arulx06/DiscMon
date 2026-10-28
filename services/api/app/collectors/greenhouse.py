from __future__ import annotations

from urllib.parse import urljoin

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


class GreenhouseAdapter(SourceAdapter):
    kind = "ats_greenhouse"
    supports_closure = True

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        base = source.config_json.get("base_url", "https://boards-api.greenhouse.io")
        return {domain_of(base) or "boards-api.greenhouse.io"}

    def request_url(self, source: SourceConfig) -> str:
        board = source.config_json.get("board_token")
        if not board:
            raise ValueError("Greenhouse source requires config.board_token")
        base = source.config_json.get("base_url", "https://boards-api.greenhouse.io").rstrip("/")
        return f"{base}/v1/boards/{board}/jobs?content=true"

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        url = self.request_url(source)
        response = await fetcher.get(url, headers=conditional_headers(source))
        content_json = None
        if response.content and response.status_code == 200:
            try:
                import json

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
            raise ValueError("Greenhouse response is missing jobs[]")
        organization = (
            source.config_json.get("organization_name")
            or payload.get("meta", {}).get("name")
            or source.name
        )
        candidates: list[NormalizedCandidate] = []
        for job in jobs:
            if not isinstance(job, dict) or job.get("id") is None:
                continue
            job_id = str(job["id"])
            title = str(job.get("title") or "Untitled role").strip()
            location = str((job.get("location") or {}).get("name") or "").strip()
            content = html_to_text(job.get("content"))
            metadata = {
                str(item.get("name", "")).lower(): item.get("value")
                for item in job.get("metadata") or []
                if isinstance(item, dict)
            }
            salary_text = None
            for key in ("salary range", "compensation", "salary"):
                if metadata.get(key):
                    salary_text = str(metadata[key])
                    break
            employment_type = None
            for key in ("employment type", "commitment"):
                if metadata.get(key):
                    employment_type = str(metadata[key])
                    break
            official_url = job.get("absolute_url") or urljoin(
                source.root_url, f"/{source.config_json.get('board_token', '')}/jobs/{job_id}"
            )
            candidate = NormalizedCandidate(
                source_external_id=job_id,
                provider_key=f"greenhouse:{job_id}",
                title=title,
                organization_name=organization,
                organization_domain=source.config_json.get("organization_domain"),
                opportunity_type=OpportunityType.job,
                description_summary=excerpt(content, 1200),
                requirements_summary=excerpt(content, 2000),
                official_url=canonicalize_url(official_url),
                application_url=canonicalize_url(official_url),
                location_text=location,
                is_remote="remote" in location.lower(),
                workplace_type="remote" if "remote" in location.lower() else "onsite",
                employment_type=employment_type,
                compensation=CompensationDTO(raw=salary_text, summary=salary_text),
                published_at=parse_datetime(job.get("updated_at")),
                source_payload={
                    "id": job_id,
                    "updated_at": job.get("updated_at"),
                    "location": job.get("location"),
                    "metadata": job.get("metadata"),
                },
                evidence_excerpt=excerpt(content, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidates.append(candidate)
        return candidates
