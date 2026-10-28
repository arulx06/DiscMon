from __future__ import annotations

import asyncio
import ipaddress
import random
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import get_settings

USER_AGENT = "DiscMon/0.1 (private personal career intelligence; low-rate; contact owner)"
MAX_REDIRECTS = 5


class FetchError(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message

    def redacted(self) -> str:
        return self.message[:500]


@dataclass
class FetchPolicy:
    allowed_hosts: set[str] = field(default_factory=set)
    min_interval_seconds: float = 0.0
    timeout_seconds: float = 20.0
    max_retries: int = 4
    max_bytes: int = 0
    allow_private: bool = False
    content_types: tuple[str, ...] = (
        "application/json",
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
        "text/html",
        "text/plain",
    )


@dataclass
class HttpResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    elapsed_ms: int
    error_class: str | None = None
    error_message: str | None = None


class _HostLimiter:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def wait(self, host: str, min_interval_seconds: float) -> None:
        if min_interval_seconds <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            previous = self._last.get(host, 0.0)
            delay = min_interval_seconds - (now - previous)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last[host] = time.monotonic()


_HOST_LIMITER = _HostLimiter()


_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if address.version == 6 and address in _NAT64_PREFIX:
        embedded = ipaddress.ip_address(int(address) & 0xFFFFFFFF)
        return _is_public_address(str(embedded))
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or (address.version == 6 and address.is_site_local)
    )


async def _resolve_host(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(
            None, lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    except socket.gaierror as exc:
        raise FetchError("dns_error", f"Could not resolve source host: {host}") from exc
    return [str(info[4][0]) for info in infos]


def _validate_url_shape(url: str, allowed_hosts: set[str], allow_private: bool) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise FetchError("blocked_ssrf", "URLs with embedded credentials are not allowed")
    if parts.scheme not in {"https", "http"}:
        raise FetchError("blocked_ssrf", "Only HTTP(S) source URLs are allowed")
    if parts.scheme == "http" and not allow_private:
        raise FetchError("blocked_ssrf", "Plain HTTP is not allowed for remote sources")
    host = (parts.hostname or "").lower()
    if not host:
        raise FetchError("invalid_url", "Source URL has no hostname")
    if allowed_hosts and host not in allowed_hosts:
        raise FetchError("host_not_allowed", f"Host is not in this source's allowlist: {host}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port


async def validate_target(url: str, policy: FetchPolicy) -> None:
    host, port = _validate_url_shape(url, policy.allowed_hosts, policy.allow_private)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not policy.allow_private and not _is_public_address(str(literal)):
            raise FetchError("blocked_ssrf", "Private, loopback or metadata address is blocked")
        return
    if policy.allow_private:
        return
    addresses = await _resolve_host(host, port)
    if not addresses:
        raise FetchError("dns_error", f"No addresses resolved for {host}")
    for address in addresses:
        if not _is_public_address(address):
            raise FetchError(
                "blocked_ssrf",
                "Source host resolves to a private or metadata address",
            )


def _retry_after_seconds(headers: dict[str, str]) -> float:
    raw = headers.get("retry-after")
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return 0.0
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - datetime.now(UTC)).total_seconds())


class SafeFetcher:
    def __init__(
        self,
        policy: FetchPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.policy = policy or FetchPolicy()
        if not self.policy.allowed_hosts:
            self.policy.allowed_hosts = set()
        self.policy.timeout_seconds = self.policy.timeout_seconds or settings.fetch_timeout_seconds
        self.policy.max_retries = self.policy.max_retries or settings.fetch_max_retries
        self.policy.max_bytes = self.policy.max_bytes or settings.max_response_bytes
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.policy.timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> SafeFetcher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        conditional: bool = True,
    ) -> HttpResponse:
        attempt = 0
        last_error: HttpResponse | None = None
        while attempt <= self.policy.max_retries:
            try:
                response = await self._request_once(
                    url, headers=headers or {}, conditional=conditional
                )
            except FetchError as exc:
                return HttpResponse(
                    url=url,
                    status_code=0,
                    headers={},
                    content=b"",
                    elapsed_ms=0,
                    error_class=exc.category,
                    error_message=exc.redacted(),
                )
            if response.status_code < 400 and response.status_code not in {429}:
                return response
            last_error = response
            if response.status_code == 403:
                break
            if response.status_code == 404:
                break
            if response.status_code == 429:
                delay = _retry_after_seconds(response.headers)
                if attempt >= self.policy.max_retries:
                    break
                await asyncio.sleep(min(delay or 2.0, 60.0))
            elif response.status_code >= 500:
                if attempt >= self.policy.max_retries:
                    break
                await asyncio.sleep(min(2**attempt + random.random(), 30.0))
            else:
                break
            attempt += 1
        return last_error or HttpResponse(
            url=url,
            status_code=0,
            headers={},
            content=b"",
            elapsed_ms=0,
            error_class="http_error",
            error_message="Source request failed",
        )

    async def _request_once(
        self, url: str, headers: dict[str, str], conditional: bool
    ) -> HttpResponse:
        current = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            await validate_target(current, self.policy)
            host = (urlsplit(current).hostname or "").lower()
            await _HOST_LIMITER.wait(host, self.policy.min_interval_seconds)
            request_headers = {"User-Agent": USER_AGENT, **headers}
            if not conditional:
                request_headers.pop("If-None-Match", None)
                request_headers.pop("If-Modified-Since", None)
            started = time.monotonic()
            try:
                response = await self._client.get(current, headers=request_headers)
            except httpx.TimeoutException as exc:
                raise FetchError("timeout", "Source request timed out") from exc
            except httpx.HTTPError as exc:
                raise FetchError(
                    "network_error",
                    f"Source request failed: {exc.__class__.__name__}",
                ) from exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("redirect_error", "Redirect had no Location header")
                current = urljoin(current, location)
                if redirect_count == MAX_REDIRECTS:
                    raise FetchError("redirect_error", "Too many redirects")
                continue
            content = response.content
            if len(content) > self.policy.max_bytes:
                raise FetchError("too_large", "Source response exceeded the configured size limit")
            content_type = (
                (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            )
            if content_type and not any(
                content_type.startswith(allowed) for allowed in self.policy.content_types
            ):
                raise FetchError("content_type", f"Unsupported source content type: {content_type}")
            return HttpResponse(
                url=str(response.url),
                status_code=response.status_code,
                headers={key.lower(): value for key, value in response.headers.items()},
                content=content,
                elapsed_ms=elapsed_ms,
            )
        raise FetchError("redirect_error", "Too many redirects")
