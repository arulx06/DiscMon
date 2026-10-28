from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "gh_src",
    "lever-source",
    "lever-origin",
    "ashby_source",
    "trackingid",
}

DEFAULT_PORTS = {"http": "80", "https": "443"}


def canonicalize_url(raw: str) -> str:
    """Return a stable official URL without collapsing distinct listings."""
    parts = urlsplit(raw.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return raw.strip()
    port = parts.port
    netloc = host
    if port and DEFAULT_PORTS.get(scheme) != str(port):
        netloc = f"{host}:{port}"
    if parts.username or parts.password:
        netloc = host
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_pairs))
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def domain_of(raw: str) -> str | None:
    host = (urlsplit(raw).hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def root_domain(raw: str) -> str | None:
    host = domain_of(raw)
    if not host:
        return None
    pieces = host.split(".")
    if len(pieces) <= 2:
        return host
    return ".".join(pieces[-2:])


def url_hash(raw: str) -> str:
    return hashlib.sha256(canonicalize_url(raw).encode("utf-8")).hexdigest()


def is_http_url(raw: str) -> bool:
    parts = urlsplit(raw)
    return parts.scheme in {"http", "https"} and bool(parts.hostname)


def title_similarity(left: str, right: str) -> float:
    """Cheap Jaccard token similarity; callers must never auto-merge on this alone."""
    left_tokens = {token for token in left.lower().split() if len(token) > 2}
    right_tokens = {token for token in right.lower().split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
