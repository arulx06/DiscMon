from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import get_adapter
from app.collectors.http import FetchPolicy, SafeFetcher
from app.db.models.audit import AuditEvent
from app.db.models.discovery import DiscoveryCandidate
from app.db.models.enums import (
    ApprovalStatus,
    LegalReviewStatus,
    Officialness,
    SourceKind,
)
from app.db.models.source import Source
from app.schemas.collector import FetchResult, SourceConfig
from app.services.text import html_to_text
from app.services.time import now_utc
from app.services.urls import canonicalize_url, domain_of, is_http_url

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}'\">"


@dataclass
class DiscoveryOutcome:
    source_id: uuid.UUID
    links_seen: int = 0
    created: int = 0
    skipped_known: int = 0
    skipped_invalid: int = 0
    candidate_ids: list[uuid.UUID] = field(default_factory=list)


def _discovery_config(source: Source) -> dict:
    config = (source.config_json or {}).get("discovery")
    return config if isinstance(config, dict) else {}


def discovery_enabled(source: Source) -> bool:
    return bool(_discovery_config(source).get("enabled"))


def discovery_cadence(source: Source) -> str | None:
    cadence = _discovery_config(source).get("cadence", "weekly")
    return cadence if isinstance(cadence, str) and cadence in {"weekly", "monthly"} else None


def _allowed_domains(source: Source) -> set[str]:
    config = _discovery_config(source)
    raw = config.get("allowed_domains")
    if raw is None:
        fallback = domain_of(source.root_url)
        return {fallback} if fallback else set()
    values = raw if isinstance(raw, list) else [raw]
    domains: set[str] = set()
    for value in values:
        text = str(value).strip().lower()
        if not text:
            continue
        if "://" not in text:
            text = f"https://{text}"
        host = domain_of(text)
        if host:
            domains.add(host.lower().rstrip("."))
    return domains


def _host_allowed(host: str, allowed: set[str]) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == domain or normalized.endswith(f".{domain}") for domain in allowed
    )


def _clean_url(value: str) -> str | None:
    text = value.strip().rstrip(TRAILING_PUNCTUATION)
    if not text or not is_http_url(text):
        return None
    parts = urlsplit(text)
    if parts.username or parts.password:
        return None
    return canonicalize_url(text)


def _fragment_links(fragment: str) -> list[str]:
    links: list[str] = []
    soup = BeautifulSoup(fragment, "html.parser")
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if href:
            links.append(str(href))
    for match in URL_PATTERN.findall(html_to_text(fragment)):
        links.append(match)
    return links


def _candidate_links(
    source: Source, result: FetchResult
) -> list[str]:
    config = _discovery_config(source)
    include_entry_links = bool(config.get("include_entry_links", False))
    links: list[str] = []
    if source.source_kind in {SourceKind.rss, SourceKind.github}:
        payload = result.content_json or {}
        entries = payload.get("entries")
        items = payload.get("items")
        if not isinstance(entries, list):
            entries = []
        if not isinstance(items, list):
            items = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if include_entry_links and entry.get("link"):
                links.append(str(entry["link"]))
            links.extend(_fragment_links(str(entry.get("summary") or "")))
        for entry in items:
            if not isinstance(entry, dict):
                continue
            raw_item = entry.get("item")
            item = raw_item if isinstance(raw_item, dict) else {}
            if include_entry_links and item.get("html_url"):
                links.append(str(item["html_url"]))
            links.extend(_fragment_links(str(item.get("body") or "")))
        return links

    if not result.raw_bytes:
        return links
    soup = BeautifulSoup(result.raw_bytes, "html.parser")
    for element in soup(["script", "style", "noscript", "iframe", "object"]):
        element.decompose()
    selector = str(config.get("link_selector") or "a[href]")
    for anchor in soup.select(selector):
        href = anchor.get("href")
        if href:
            links.append(urljoin(source.root_url, str(href)))
    return links


def suggest_source_kind(url: str) -> SourceKind:
    host = (domain_of(url) or "").lower()
    path = (urlsplit(url).path or "").lower()
    if host.endswith("greenhouse.io"):
        return SourceKind.ats_greenhouse
    if host.endswith("lever.co"):
        return SourceKind.ats_lever
    if host.endswith("ashbyhq.com"):
        return SourceKind.ats_ashby
    if path.endswith((".rss", ".atom", ".xml")) or "/feed" in path:
        return SourceKind.rss
    return SourceKind.static_html


async def promote_candidate(
    session: AsyncSession, candidate_id: uuid.UUID
) -> tuple[Source, bool]:
    candidate = await session.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise ValueError("Discovery candidate does not exist")
    if candidate.approval_status != ApprovalStatus.approved:
        raise ValueError("Discovery candidate must be approved before promotion")
    if candidate.promoted_source_id is not None:
        source = await session.get(Source, candidate.promoted_source_id)
        if source is not None:
            return source, False
    canonical = canonicalize_url(candidate.candidate_url)
    existing = await session.scalar(select(Source).where(Source.root_url == canonical))
    if existing is not None:
        candidate.promoted_source_id = existing.id
        await session.flush()
        return existing, False
    host = domain_of(canonical)
    if not host:
        raise ValueError("Discovery candidate URL has no host")
    source = Source(
        name=host,
        source_kind=candidate.suggested_adapter or SourceKind.static_html,
        root_url=canonical,
        config_json={},
        officialness=candidate.officialness_guess,
        enabled=False,
        approval_status=ApprovalStatus.approved,
        legal_review_status=LegalReviewStatus.pending,
        interval_hours=24,
        next_due_at=None,
    )
    session.add(source)
    await session.flush()
    candidate.promoted_source_id = source.id
    await session.flush()
    return source, True


async def run_discovery(session: AsyncSession, source_id: uuid.UUID) -> DiscoveryOutcome:
    source = await session.get(Source, source_id)
    if source is None:
        raise ValueError("Discovery source does not exist")
    if not source.enabled:
        raise ValueError("Discovery source is disabled")
    if (
        source.approval_status != ApprovalStatus.approved
        or source.legal_review_status != LegalReviewStatus.approved
    ):
        raise ValueError("Discovery source requires approval and legal review")
    config = _discovery_config(source)
    if not config.get("enabled"):
        raise ValueError("Source configuration does not enable discovery")
    allowed_domains = _allowed_domains(source)
    if not allowed_domains:
        raise ValueError("Discovery requires at least one allowed domain")
    max_candidates = max(1, min(int(config.get("max_candidates", 25)), 100))

    adapter = get_adapter(source.source_kind.value)
    source_config = SourceConfig(
        id=source.id,
        name=source.name,
        source_kind=source.source_kind,
        root_url=source.root_url,
        config_json=source.config_json or {},
        officialness=source.officialness.value,
        rate_limit_json=source.rate_limit_json or {},
    )
    policy = FetchPolicy(
        allowed_hosts=adapter.allowed_hosts(source_config),
        timeout_seconds=20,
        max_retries=2,
    )
    fetcher = SafeFetcher(policy)
    try:
        result = await adapter.fetch(source_config, fetcher)
    finally:
        await fetcher.close()
    if result.error_class or not result.ok:
        raise RuntimeError(
            result.error_message or f"Discovery fetch returned HTTP {result.http_status}"
        )
    if result.not_modified:
        return DiscoveryOutcome(source_id=source.id)

    raw_links = _candidate_links(source, result)
    existing_sources = set(
        (await session.scalars(select(Source.root_url))).all()
    )
    existing_candidates = set(
        (await session.scalars(select(DiscoveryCandidate.candidate_url))).all()
    )
    source_host = (domain_of(source.root_url) or "").lower()
    outcome = DiscoveryOutcome(source_id=source.id, links_seen=len(raw_links))
    seen: set[str] = set()
    for raw in raw_links:
        cleaned = _clean_url(raw)
        if cleaned is None:
            outcome.skipped_invalid += 1
            continue
        if cleaned in seen or cleaned == canonicalize_url(source.root_url):
            continue
        seen.add(cleaned)
        host = (domain_of(cleaned) or "").lower()
        if not host or not _host_allowed(host, allowed_domains):
            outcome.skipped_invalid += 1
            continue
        if cleaned in existing_sources or cleaned in existing_candidates:
            outcome.skipped_known += 1
            continue
        if outcome.created >= max_candidates:
            break
        candidate = DiscoveryCandidate(
            candidate_url=cleaned,
            found_via_source_id=source.id,
            discovered_at=now_utc(),
            candidate_type="programme_link",
            suggested_adapter=suggest_source_kind(cleaned),
            officialness_guess=(
                Officialness.official if host == source_host else Officialness.unknown
            ),
            approval_status=ApprovalStatus.candidate,
            legal_review_status=LegalReviewStatus.pending,
            notes=f"Discovered from approved source {source.name[:180]}; review before enabling.",
        )
        session.add(candidate)
        await session.flush()
        existing_candidates.add(cleaned)
        outcome.created += 1
        outcome.candidate_ids.append(candidate.id)

    session.add(
        AuditEvent(
            actor="system",
            event_type="discovery.scanned",
            entity_type="source",
            entity_id=source.id,
            after_json={
                "links_seen": outcome.links_seen,
                "created": outcome.created,
                "skipped_known": outcome.skipped_known,
                "skipped_invalid": outcome.skipped_invalid,
            },
        )
    )
    await session.flush()
    return outcome
