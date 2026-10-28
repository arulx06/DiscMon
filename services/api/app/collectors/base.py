from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime

from app.collectors.http import HttpResponse, SafeFetcher
from app.schemas.collector import (
    DiscoveredURL,
    FetchResult,
    NormalizedCandidate,
    SourceConfig,
)
from app.services.time import now_utc


class SourceAdapter(ABC):
    kind: str
    supports_closure = False

    @abstractmethod
    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        raise NotImplementedError

    async def discover(self, source: SourceConfig) -> list[DiscoveredURL]:
        return [DiscoveredURL(url=source.root_url)]

    @abstractmethod
    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        raise NotImplementedError

    @abstractmethod
    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        raise NotImplementedError


def fetch_result_from_response(
    source: SourceConfig,
    response: HttpResponse,
    *,
    content_json: dict | None = None,
    scan_complete: bool = False,
    source_url: str | None = None,
) -> FetchResult:
    now = now_utc()
    error_class = response.error_class
    error_message = response.error_message
    if response.status_code == 304:
        return FetchResult(
            source_id=source.id,
            fetched_at=now,
            http_status=304,
            content_type=response.headers.get("content-type"),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            raw_hash=hashlib.sha256(response.content).hexdigest(),
            content_json=content_json or {},
            scan_complete=False,
            not_modified=True,
            source_url=source_url or source.root_url,
        )
    if response.status_code >= 400 and error_class is None:
        error_class = "http_error"
        error_message = f"Source returned HTTP {response.status_code}"
    return FetchResult(
        source_id=source.id,
        fetched_at=now,
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        raw_hash=hashlib.sha256(response.content).hexdigest() if response.content else None,
        content_json=content_json,
        scan_complete=scan_complete and response.status_code == 200,
        source_url=source_url or source.root_url,
        error_class=error_class,
        error_message=error_message,
        raw_bytes=response.content,
    )


def conditional_headers(source: SourceConfig) -> dict[str, str]:
    cache = source.config_json.get("http_cache") if isinstance(source.config_json, dict) else {}
    headers: dict[str, str] = {}
    if isinstance(cache, dict):
        if cache.get("etag"):
            headers["If-None-Match"] = str(cache["etag"])
        if cache.get("last_modified"):
            headers["If-Modified-Since"] = str(cache["last_modified"])
    return headers


def published_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None
