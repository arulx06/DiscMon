from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import feedparser

from app.collectors.base import (
    SourceAdapter,
    conditional_headers,
    fetch_result_from_response,
)
from app.collectors.http import SafeFetcher
from app.schemas.collector import FetchResult, NormalizedCandidate, SourceConfig
from app.services.eligibility import infer_country_codes, infer_remote_countries
from app.services.normalize import classify_opportunity, parse_compensation_text
from app.services.text import excerpt, html_to_text
from app.services.time import extract_deadline_from_text, now_utc
from app.services.urls import canonicalize_url, domain_of


def _entry_datetime(entry: dict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(value[0], value[1], value[2], value[3], value[4], value[5], tzinfo=UTC)
    return None


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
            deadline = extract_deadline_from_text(summary_text, now_utc())
            candidate = NormalizedCandidate(
                source_external_id=external_id,
                provider_key=f"url:{canonical}",
                title=title,
                organization_name=str(feed_title),
                organization_domain=domain_of(canonical),
                opportunity_type=classify_opportunity(title, summary_text),
                description_summary=excerpt(summary_text, 1200),
                requirements_summary=excerpt(summary_text, 2000),
                official_url=canonical,
                application_url=canonical,
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
