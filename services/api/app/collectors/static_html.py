from __future__ import annotations

import hashlib
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.collectors.base import (
    SourceAdapter,
    conditional_headers,
    fetch_result_from_response,
)
from app.collectors.http import SafeFetcher
from app.schemas.collector import FetchResult, NormalizedCandidate, SourceConfig
from app.services.eligibility import infer_country_codes, infer_remote_countries
from app.services.normalize import classify_opportunity, parse_compensation_text
from app.services.text import detect_employment_conflict, excerpt, normalize_whitespace
from app.services.time import extract_deadline_from_text, now_utc
from app.services.urls import canonicalize_url, domain_of


class StaticHTMLAdapter(SourceAdapter):
    kind = "static_html"
    supports_closure = False

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        return {domain_of(source.root_url) or ""}

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        response = await fetcher.get(source.root_url, headers=conditional_headers(source))
        return fetch_result_from_response(
            source,
            response,
            content_json=None,
            scan_complete=False,
            source_url=source.root_url,
        )

    def _item_candidates(
        self, source: SourceConfig, soup: BeautifulSoup, result: FetchResult
    ) -> list[NormalizedCandidate]:
        config = source.config_json
        item_selector = config.get("item_selector")
        if not item_selector:
            return []
        title_selector = config.get("title_selector", "h2, h3, h4, a")
        link_selector = config.get("link_selector", "a[href]")
        date_selector = config.get("date_selector")
        org_name = config.get("organization_name") or source.name
        candidates: list[NormalizedCandidate] = []
        for node in soup.select(str(item_selector))[:200]:
            title_node = node.select_one(str(title_selector))
            link_node = node.select_one(str(link_selector))
            title = normalize_whitespace(title_node.get_text(" ", strip=True) if title_node else "")
            href = link_node.get("href") if link_node else None
            if not title or not href:
                continue
            official_url = canonicalize_url(urljoin(source.root_url, str(href)))
            item_text = normalize_whitespace(node.get_text(" ", strip=True))
            date_text = ""
            if date_selector:
                date_node = node.select_one(str(date_selector))
                if date_node:
                    date_text = date_node.get_text(" ", strip=True)
            deadline = extract_deadline_from_text(
                " ".join(filter(None, [date_text, item_text[:1500]])), now_utc()
            )
            candidate = NormalizedCandidate(
                source_external_id=hashlib.sha256(official_url.encode("utf-8")).hexdigest()[:32],
                provider_key=f"url:{official_url}",
                title=title,
                organization_name=org_name,
                organization_domain=domain_of(official_url),
                opportunity_type=classify_opportunity(title, item_text),
                description_summary=excerpt(item_text, 1200),
                requirements_summary=excerpt(item_text, 2000),
                official_url=official_url,
                application_url=official_url,
                location_text=config.get("location_text"),
                is_remote=bool(config.get("remote", False)),
                compensation=parse_compensation_text(item_text),
                deadline_on=deadline["deadline_on"],
                deadline_at=deadline["deadline_at"],
                deadline_timezone=deadline["deadline_timezone"],
                deadline_precision=deadline["deadline_precision"],
                source_payload={"item_text_hash": hashlib.sha256(item_text.encode()).hexdigest()},
                evidence_excerpt=excerpt(item_text, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidate.employment_conflict = detect_employment_conflict(
                item_text, candidate.opportunity_type.value
            )
            candidates.append(candidate)
        return candidates

    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        if not result.raw_bytes:
            raise ValueError("Static source returned no body to parse")
        soup = BeautifulSoup(result.raw_bytes, "html.parser")
        for element in soup(["script", "style", "noscript", "iframe", "object"]):
            element.decompose()
        candidates = self._item_candidates(source, soup, result)
        if candidates:
            return candidates
        config = source.config_json
        title_node = soup.select_one(str(config.get("title_selector", "h1"))) or soup.find("title")
        title = normalize_whitespace(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            title = source.name
        description_node = soup.select_one(
            str(config.get("description_selector", "main, article, .content, body"))
        )
        body_text = normalize_whitespace(
            description_node.get_text(" ", strip=True)
            if description_node
            else soup.get_text(" ", strip=True)
        )
        deadline = extract_deadline_from_text(body_text, now_utc())
        location_text = config.get("location_text")
        canonical = canonicalize_url(source.root_url)
        candidate = NormalizedCandidate(
            source_external_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32],
            provider_key=f"url:{canonical}",
            title=title,
            organization_name=config.get("organization_name") or source.name,
            organization_domain=domain_of(canonical),
            opportunity_type=classify_opportunity(title, body_text),
            description_summary=excerpt(body_text, 1500),
            requirements_summary=excerpt(body_text, 2500),
            official_url=canonical,
            application_url=canonical,
            location_text=location_text,
            is_remote=bool(config.get("remote", False)),
            compensation=parse_compensation_text(body_text),
            deadline_on=deadline["deadline_on"],
            deadline_at=deadline["deadline_at"],
            deadline_timezone=deadline["deadline_timezone"],
            deadline_precision=deadline["deadline_precision"],
            source_payload={"page_hash": result.raw_hash},
            evidence_excerpt=excerpt(body_text, 600),
        )
        candidate.country_codes = infer_country_codes(candidate)
        candidate.allowed_remote_countries = infer_remote_countries(candidate)
        candidate.employment_conflict = detect_employment_conflict(
            body_text, candidate.opportunity_type.value
        )
        return [candidate]


class ManualAdapter(StaticHTMLAdapter):
    kind = "manual"


class ChangedetectionAdapter(StaticHTMLAdapter):
    kind = "changedetection"
