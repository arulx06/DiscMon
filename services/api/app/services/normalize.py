from __future__ import annotations

import re

from app.db.models.enums import OpportunityType
from app.schemas.collector import CompensationDTO

CURRENCY_TOKEN = r"(?:INR|Rs\.?|USD|EUR|GBP|[€£₹$])"
AMOUNT_NUMBER = r"\d[\d,]*(?:\.\d+)?"
AMOUNT_RANGE = rf"{AMOUNT_NUMBER}(?:\s*(?:-|–|—|to)\s*{AMOUNT_NUMBER})?"
PAY_UNIT = r"(?:LPA|lakhs?|lacs?)"
PAY_PERIOD = (
    r"(?:(?:per|a|an|each)\s+(?:month|year|annum|week|day|hour)|"
    r"/\s*(?:month|year|week|day|hour)|monthly|annual(?:ly)?|weekly|daily|hourly)"
)
CURRENCY_AMOUNT_PATTERN = re.compile(
    rf"(?P<currency>{CURRENCY_TOKEN})\s*(?P<amount>{AMOUNT_RANGE})"
    rf"(?:\s*(?P<unit>{PAY_UNIT}))?(?:\s*(?P<period>{PAY_PERIOD}))?",
    re.IGNORECASE,
)
LPA_AMOUNT_PATTERN = re.compile(
    rf"(?P<amount>{AMOUNT_RANGE})\s*(?P<unit>LPA|lakhs?|lacs?)\b",
    re.IGNORECASE,
)
PAY_LABEL_PATTERN = re.compile(
    r"\b(?:salary|compensation|stipend|remuneration|pay|paid|ctc|honorarium)\b",
    re.IGNORECASE,
)
CREDIT_PATTERN = re.compile(r"\b(\d[\d,.]*)\s*(?:cloud\s+)?credits?\b", re.IGNORECASE)
EQUITY_PATTERN = re.compile(r"\b(?:equity|esops?|stock options?|rsus?)\b", re.IGNORECASE)


JOB_TITLE_WORDS = (
    "job",
    "engineer",
    "engineering",
    "developer",
    "sre",
    "architect",
    "manager",
    "designer",
    "design",
    "associate",
    "analyst",
    "scientist",
    "administrator",
    "consultant",
    "specialist",
    "director",
    "executive",
    "intern",
    "sales",
    "head",
)


def classify_opportunity(title: str, text: str | None = None) -> OpportunityType:
    title_lower = title.lower()
    if "fellowship" in title_lower or "fellow" in title_lower:
        return OpportunityType.fellowship
    if "residency" in title_lower or "resident" in title_lower:
        return OpportunityType.residency
    if "mentorship" in title_lower or "mentor" in title_lower:
        return OpportunityType.mentorship
    if "hackathon" in title_lower:
        return OpportunityType.hackathon
    if "competition" in title_lower or "challenge" in title_lower:
        return OpportunityType.competition
    if "grant" in title_lower or "scholarship" in title_lower:
        return OpportunityType.grant
    if "accelerator" in title_lower or "founder" in title_lower:
        return OpportunityType.founder_programme
    if any(word in title_lower for word in JOB_TITLE_WORDS):
        return OpportunityType.job

    lowered = f"{title} {text or ''}".lower()
    if "fellowship" in lowered:
        return OpportunityType.fellowship
    if "residency" in lowered or "resident" in lowered:
        return OpportunityType.residency
    if "mentorship" in lowered or "mentor" in lowered:
        return OpportunityType.mentorship
    if "hackathon" in lowered:
        return OpportunityType.hackathon
    if "competition" in lowered or "challenge" in lowered:
        return OpportunityType.competition
    if "grant" in lowered or "scholarship" in lowered:
        return OpportunityType.grant
    if "accelerator" in lowered or "founder" in lowered or "founding" in lowered:
        return OpportunityType.founder_programme
    if any(word in lowered for word in ("job", "engineer", "developer", "sre", "architect")):
        return OpportunityType.job
    if "program" in lowered or "programme" in lowered or "cohort" in lowered:
        return OpportunityType.programme
    return OpportunityType.other


def _period_label(value: str | None, unit: str | None) -> str | None:
    if unit and unit.lower() in {"lpa", "lakh", "lakhs", "lac", "lacs"}:
        return "per year"
    if not value:
        return None
    lowered = value.lower()
    if "month" in lowered or lowered == "monthly":
        return "per month"
    if "year" in lowered or "annual" in lowered:
        return "per year"
    if "week" in lowered:
        return "per week"
    if "day" in lowered:
        return "per day"
    if "hour" in lowered:
        return "per hour"
    return value


def _compensation_snippet(normalized: str, start: int, end: int, label_start: int | None) -> str:
    if label_start is not None:
        snippet_start = label_start
    else:
        snippet_start = start
        prefix_start = max(
            normalized.rfind(".", 0, snippet_start),
            normalized.rfind(";", 0, snippet_start),
            normalized.rfind("•", 0, snippet_start),
        )
        if prefix_start >= 0 and snippet_start - prefix_start < 80:
            snippet_start = prefix_start + 1
    tail = normalized[end : end + 160]
    boundaries = [
        index for marker in (".", ";", "•") if (index := tail.find(marker)) >= 0
    ]
    label_boundary = re.search(
        r"\s+(?:deadline|location|mode|type|requirements?|eligibility|duration|"
        r"apply|process|about|starts?|what)\s*:",
        tail,
        flags=re.IGNORECASE,
    )
    if label_boundary:
        boundaries.append(label_boundary.start())
    benefit_boundary = re.search(
        r"\s+(?:direct access|hands-on|time with|a project|mentorship|"
        r"learning and|exposure to|networking|professional development)\b",
        tail,
        flags=re.IGNORECASE,
    )
    if benefit_boundary:
        boundaries.append(benefit_boundary.start())
    snippet_end = end + min(boundaries) if boundaries else min(end + 160, len(normalized))
    return normalized[snippet_start:snippet_end].strip(" ,;•")


def parse_compensation_text(text: str | None) -> CompensationDTO:
    if not text:
        return CompensationDTO()
    normalized = " ".join(text.split())

    candidates: list[tuple[int, int, int, int | None, re.Match[str]]] = []
    for pattern in (CURRENCY_AMOUNT_PATTERN, LPA_AMOUNT_PATTERN):
        for match in pattern.finditer(normalized):
            label_matches = list(PAY_LABEL_PATTERN.finditer(normalized, 0, match.end()))
            label_start = label_matches[-1].start() if label_matches else None
            label_near = label_start is not None and match.start() - label_start <= 140
            lpa_alone = (match.groupdict().get("unit") or "").lower() == "lpa"
            if not label_near and not lpa_alone:
                continue
            distance = (
                match.start() - label_start
                if label_near and label_start is not None
                else match.start()
            )
            unit_priority = 0 if lpa_alone else 1
            candidates.append((unit_priority, distance, match.start(), label_start, match))
    if not candidates:
        return CompensationDTO()

    _, _, _, label_start, match = min(candidates, key=lambda item: item[:3])
    snippet = _compensation_snippet(normalized, match.start(), match.end(), label_start)
    if not snippet:
        return CompensationDTO()
    groups = match.groupdict()
    cash = " ".join(
        part for part in (groups.get("currency"), groups.get("amount"), groups.get("unit")) if part
    )
    credit = CREDIT_PATTERN.search(snippet)
    equity = EQUITY_PATTERN.search(snippet)
    return CompensationDTO(
        cash=cash,
        equity=equity.group(0) if equity else None,
        credits=credit.group(0) if credit else None,
        currency=groups.get("currency"),
        period=_period_label(groups.get("period"), groups.get("unit")),
        summary=snippet[:300],
        raw=snippet[:500],
    )
