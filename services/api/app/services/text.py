from __future__ import annotations

import re
import unicodedata

import bleach
from bs4 import BeautifulSoup

WHITESPACE = re.compile(r"\s+")


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    for element in soup(["script", "style", "noscript", "iframe", "object"]):
        element.decompose()
    text = soup.get_text(" ", strip=True)
    return normalize_whitespace(text)


def normalize_whitespace(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return WHITESPACE.sub(" ", normalized).strip()


def excerpt(value: str | None, limit: int = 600) -> str | None:
    text = normalize_whitespace(value or "")
    if not text:
        return None
    return text[:limit]


def sanitize_inline_html(value: str | None) -> str:
    """Allow only harmless formatting; all source text is untrusted data."""
    if not value:
        return ""
    return bleach.clean(
        value,
        tags=["p", "br", "strong", "em", "ul", "ol", "li", "a"],
        attributes={"a": ["href", "rel"]},
        protocols=["https", "http"],
        strip=True,
    )


def detect_employment_conflict(text: str, opportunity_type: str) -> bool:
    lowered = text.lower()
    if opportunity_type == "job":
        return False
    full_time = any(
        phrase in lowered
        for phrase in (
            "full-time commitment",
            "full time commitment",
            "commit full-time",
            "full-time program",
            "full-time programme",
            "must not hold another job",
            "exclusive commitment",
        )
    )
    interruption = any(
        phrase in lowered
        for phrase in (
            "leave your job",
            "quit your job",
            "career break",
            "relocate for the duration",
        )
    )
    return full_time or interruption
