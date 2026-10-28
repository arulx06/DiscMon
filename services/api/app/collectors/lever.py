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


class LeverAdapter(SourceAdapter):
    kind = "ats_lever"
    supports_closure = True

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        base = source.config_json.get("base_url")
        if base:
            return {domain_of(base) or "api.lever.co"}
        region = source.config_json.get("region", "global")
        return {"api.eu.lever.co" if region == "eu" else "api.lever.co"}

    def request_url(self, source: SourceConfig) -> str:
        site = source.config_json.get("site")
        if not site:
            raise ValueError("Lever source requires config.site")
        base = source.config_json.get("base_url")
        if not base:
            base = (
                "https://api.eu.lever.co"
                if source.config_json.get("region") == "eu"
                else "https://api.lever.co"
            )
        return f"{base.rstrip('/')}/v0/postings/{site}?mode=json"

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        url = self.request_url(source)
        response = await fetcher.get(url, headers=conditional_headers(source))
        content_json = None
        if response.content and response.status_code == 200:
            try:
                content_json = {"postings": json.loads(response.content)}
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
        postings = payload.get("postings")
        if not isinstance(postings, list):
            raise ValueError("Lever response is not a posting array")
        organization = source.config_json.get("organization_name") or source.name
        candidates: list[NormalizedCandidate] = []
        for posting in postings:
            if not isinstance(posting, dict) or posting.get("id") is None:
                continue
            external_id = str(posting["id"])
            categories = posting.get("categories") or {}
            location = str(categories.get("location") or "").strip()
            all_locations = posting.get("allLocations") or []
            if isinstance(all_locations, list) and all_locations:
                location = ", ".join(str(item) for item in all_locations)
            description = html_to_text(
                posting.get("descriptionPlain") or posting.get("description") or ""
            )
            lists = posting.get("lists") or []
            list_text = " ".join(
                html_to_text(item.get("text") or "") + " " + html_to_text(item.get("content") or "")
                for item in lists
                if isinstance(item, dict)
            )
            salary = posting.get("salaryRange") or {}
            cash = None
            currency = None
            period = None
            if isinstance(salary, dict):
                minimum = salary.get("min")
                maximum = salary.get("max")
                currency = salary.get("currency")
                period = salary.get("interval")
                if minimum or maximum:
                    cash = (
                        f"{minimum or '?'}–{maximum or '?'} {currency or ''} "
                        f"per {period or 'period'}"
                    )
            official_url = posting.get("hostedUrl") or posting.get("applyUrl")
            if not official_url:
                continue
            candidate = NormalizedCandidate(
                source_external_id=external_id,
                provider_key=f"lever:{external_id}",
                title=str(posting.get("text") or "Untitled role").strip(),
                organization_name=organization,
                organization_domain=source.config_json.get("organization_domain"),
                opportunity_type=OpportunityType.job,
                description_summary=excerpt(description, 1200),
                requirements_summary=excerpt(list_text or description, 2000),
                official_url=canonicalize_url(official_url),
                application_url=canonicalize_url(posting.get("applyUrl") or official_url),
                location_text=location,
                is_remote="remote" in location.lower(),
                workplace_type=(
                    str(posting.get("workplaceType") or "").lower()
                    or ("remote" if "remote" in location.lower() else "onsite")
                ),
                employment_type=categories.get("commitment"),
                compensation=CompensationDTO(
                    cash=cash,
                    currency=currency,
                    period=period,
                    summary=cash,
                    raw=str(salary) if salary else None,
                ),
                published_at=parse_datetime(posting.get("createdAt")),
                source_payload={
                    "id": external_id,
                    "categories": categories,
                    "createdAt": posting.get("createdAt"),
                },
                evidence_excerpt=excerpt(description or list_text, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidates.append(candidate)
        return candidates
