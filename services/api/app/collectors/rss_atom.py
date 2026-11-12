from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

import feedparser
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
from app.services.text import excerpt, html_to_text, normalize_whitespace
from app.services.time import extract_deadline_from_text, now_utc
from app.services.urls import canonicalize_url, domain_of

EMPLOYMENT_TYPE_PATTERN = re.compile(
    r"\b(?:employment\s+type|job\s+type|type)\s*[:=-]\s*"
    r"(full[\s-]?time|part[\s-]?time|contract(?:or)?|internship|temporary|freelance)\b",
    re.IGNORECASE,
)
EMPLOYMENT_TYPE_LABELS = {
    "fulltime": "FullTime",
    "parttime": "PartTime",
    "contract": "Contract",
    "contractor": "Contract",
    "internship": "Internship",
    "temporary": "Temporary",
    "freelance": "Freelance",
}


def _entry_datetime(entry: dict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(value[0], value[1], value[2], value[3], value[4], value[5], tzinfo=UTC)
    return None


def _employment_type(text: str) -> str | None:
    match = EMPLOYMENT_TYPE_PATTERN.search(text)
    if not match:
        return None
    key = re.sub(r"[\s-]+", "", match.group(1).lower())
    return EMPLOYMENT_TYPE_LABELS.get(key)


def _workplace_type(location_text: str | None) -> str | None:
    location = (location_text or "").lower()
    if "hybrid" in location:
        return "hybrid"
    if "remote" in location:
        return "remote"
    if any(marker in location for marker in ("onsite", "on-site", "in-office", "in office")):
        return "onsite"
    return None


def _summary_organization(summary: str | None) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(summary or "", "html.parser")
    anchor = soup.select_one("strong a[href]")
    if anchor is None:
        return None, None
    name = normalize_whitespace(anchor.get_text(" ", strip=True))
    href = str(anchor.get("href") or "")
    return (name or None), (domain_of(href) if href else None)


class RSSAtomAdapter(SourceAdapter):
    kind = "rss"
    supports_closure = False

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        return {domain_of(source.root_url) or ""}

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        response = await fetcher.get(source.root_url, headers=conditional_headers(source))
        parsed = None
        if response.content and response.status_code == 200:
            feed = feedparser.parse(response.content)
            if feed.get("bozo") and not feed.get("entries"):
                return fetch_result_from_response(
                    source,
                    response,
                    content_json=None,
                    scan_complete=False,
                    source_url=source.root_url,
                )
            parsed = {
                "feed": {
                    "title": feed.feed.get("title") if feed.get("feed") else None,
                    "link": feed.feed.get("link") if feed.get("feed") else source.root_url,
                },
                "entries": [
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title"),
                        "link": entry.get("link"),
                        "summary": entry.get("summary") or entry.get("description"),
                        "location": entry.get("location"),
                        "published_parsed": list(entry.get("published_parsed") or []),
                        "updated_parsed": list(entry.get("updated_parsed") or []),
                        "author": entry.get("author"),
                    }
                    for entry in feed.entries
                ],
            }
        return fetch_result_from_response(
            source,
            response,
            content_json=parsed,
            scan_complete=False,
            source_url=source.root_url,
        )

    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        payload = result.content_json or {}
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise ValueError("Feed parser produced no entries array")
        feed_title = (payload.get("feed") or {}).get("title") or source.name
        candidates: list[NormalizedCandidate] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            link = entry.get("link")
            title = str(entry.get("title") or "").strip()
            if not link or not title:
                continue
            published = None
            for key in ("published_parsed", "updated_parsed"):
                values = entry.get(key)
                if values:
                    try:
                        published = datetime(
                            values[0],
                            values[1],
                            values[2],
                            values[3],
                            values[4],
                            values[5],
                            tzinfo=UTC,
                        )
                    except (IndexError, TypeError, ValueError):
                        published = None
                    break
            canonical = canonicalize_url(str(link))
            external_id = (
                str(entry.get("id"))
                if entry.get("id")
                else hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
            )
            summary_text = html_to_text(entry.get("summary"))
            location_match = re.search(
                r"\blocation:\s*(.+?)(?=\s+(?:type|company|deadline):|$)",
                summary_text,
                flags=re.IGNORECASE,
            )
            author = str(entry.get("author") or "").strip()
            summary_org, summary_domain = _summary_organization(entry.get("summary"))
            title_org_match = re.search(r"\s+at\s+(.+?)(?:,\s|$)", title, flags=re.IGNORECASE)
            title_org = normalize_whitespace(title_org_match.group(1)) if title_org_match else None
            organization_name = author or summary_org or title_org or feed_title
            organization_domain = None
            if summary_org and summary_domain:
                organization_domain = summary_domain
            elif not author and not summary_org and not title_org:
                organization_domain = domain_of(canonical)
            entry_location = normalize_whitespace(str(entry.get("location") or ""))
            location_text = entry_location or (
                normalize_whitespace(location_match.group(1)) if location_match else None
            )
            deadline = extract_deadline_from_text(summary_text, published or now_utc())
            candidate = NormalizedCandidate(
                source_external_id=external_id,
                provider_key=f"url:{canonical}",
                title=title,
                organization_name=organization_name,
                organization_domain=organization_domain,
                opportunity_type=classify_opportunity(title, summary_text),
                description_summary=excerpt(summary_text, 1200),
                requirements_summary=excerpt(summary_text, 2000),
                official_url=canonical,
                application_url=canonical,
                location_text=location_text or None,
                workplace_type=_workplace_type(location_text) or "unknown",
                employment_type=_employment_type(summary_text),
                compensation=parse_compensation_text(summary_text),
                published_at=published,
                deadline_on=deadline["deadline_on"],
                deadline_at=deadline["deadline_at"],
                deadline_timezone=deadline["deadline_timezone"],
                deadline_precision=deadline["deadline_precision"],
                source_payload={"rss_id": entry.get("id"), "link": link},
                evidence_excerpt=excerpt(summary_text, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidate.is_remote = (
                "remote" in (candidate.location_text or "").lower()
                or "remote" in summary_text.lower()
            )
            candidates.append(candidate)
        return candidates
