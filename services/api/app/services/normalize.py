from __future__ import annotations

import re

from app.db.models.enums import OpportunityType
from app.schemas.collector import CompensationDTO

MONEY_PATTERN = re.compile(
    r"(?P<currency>[$€£₹]|USD|EUR|GBP|INR)\s?(?P<amount>\d[\d,.]*(?:\s?[kKmM])?)"
)
CREDIT_PATTERN = re.compile(r"\b(\d[\d,.]*)\s*(?:cloud\s+)?credits?\b", re.IGNORECASE)
EQUITY_PATTERN = re.compile(r"\b(?:equity|stock options?|rsus?)\b", re.IGNORECASE)


def classify_opportunity(title: str, text: str | None = None) -> OpportunityType:
    lowered = f"{title} {text or ''}".lower()
    if "fellowship" in lowered:
        return OpportunityType.fellowship
    if "residency" in lowered or "resident" in lowered:
        return OpportunityType.residency
    if "mentorship" in lowered or "mentor" in lowered:
        return OpportunityType.mentorship
    if "hackathon" in lowered or "hackathon" in title.lower():
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


def parse_compensation_text(text: str | None) -> CompensationDTO:
    if not text:
        return CompensationDTO()
    normalized = " ".join(text.split())
    money = MONEY_PATTERN.search(normalized)
    credit = CREDIT_PATTERN.search(normalized)
    equity = EQUITY_PATTERN.search(normalized)
    cash = money.group(0) if money and not equity else None
    period = None
    lowered = normalized.lower()
    for candidate in (
        "per month",
        "monthly",
        "per year",
        "annual",
        "annually",
        "per week",
        "weekly",
    ):
        if candidate in lowered:
            period = candidate
            break
    return CompensationDTO(
        cash=cash,
        equity=equity.group(0) if equity else None,
        credits=credit.group(0) if credit else None,
        currency=money.group("currency") if money else None,
        period=period,
        summary=normalized[:500],
        raw=normalized[:1000],
    )
