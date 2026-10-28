from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment
from app.db.models.digest import Digest
from app.db.models.enums import (
    DigestKind,
    EligibilityStatus,
    HealthStatus,
    LifeState,
    RecommendationBucket,
    UserDecision,
)
from app.db.models.opportunity import Opportunity, Organization
from app.db.models.source import Source
from app.services.time import days_until, now_utc
from app.services.urls import is_http_url

IST = ZoneInfo("Asia/Kolkata")
TOP_FIND_LIMIT = 5
SECTION_LIMIT = 10
MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]#<>|])")


def _latest_assessment_id():
    return (
        select(Assessment.id)
        .where(Assessment.opportunity_id == Opportunity.id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .limit(1)
        .correlate(Opportunity)
        .scalar_subquery()
    )


def digest_window(kind: DigestKind, reference: datetime | None = None) -> tuple[datetime, datetime]:
    now = (reference or now_utc()).astimezone(IST)
    start_of_day = datetime.combine(now.date(), time.min, tzinfo=IST)
    if kind == DigestKind.daily:
        start = start_of_day
        end = start + timedelta(days=1)
    else:
        start = start_of_day - timedelta(days=now.weekday())
        end = start + timedelta(days=7)
    return start.astimezone(UTC), end.astimezone(UTC)


def _escape_markdown(value: object, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return MARKDOWN_SPECIAL.sub(r"\\\1", text)[:limit]


def _safe_url(value: str | None) -> str | None:
    return value if value and is_http_url(value) else None


def _deadline_label(opportunity: Opportunity) -> str:
    precision = opportunity.deadline_precision.value
    if precision == "exact" and opportunity.deadline_at is not None:
        local = opportunity.deadline_at.astimezone(IST)
        return f"{local.strftime('%Y-%m-%d %H:%M')} IST"
    if precision == "month_only" and opportunity.deadline_on is not None:
        return f"{opportunity.deadline_on.strftime('%Y-%m')} (month only; exact date not published)"
    if opportunity.deadline_on is not None:
        return f"{opportunity.deadline_on.isoformat()} (date only; time not published)"
    return "Not published"


def _next_action(bucket: RecommendationBucket | None, hard_gate: str | None) -> str:
    if hard_gate == "needs_verification":
        return "Verify eligibility and deadline on the official source"
    if bucket == RecommendationBucket.act_now:
        return "Review the official source and apply if the terms still match"
    if bucket == RecommendationBucket.prepare_early:
        return "Start preparation early; confirm eligibility and deadline"
    if bucket == RecommendationBucket.needs_verification:
        return "Resolve the unknown eligibility or deadline before acting"
    if bucket == RecommendationBucket.keep_on_radar:
        return "Keep on the radar and recheck when the next window is announced"
    return "Review and decide whether this is worth pursuing"


def _item(
    opportunity: Opportunity,
    organization: Organization | None,
    assessment: Assessment | None,
) -> dict:
    bucket = (
        assessment.recommended_bucket if assessment else RecommendationBucket.needs_verification
    )
    hard_gate = assessment.hard_gate_status.value if assessment else None
    return {
        "id": str(opportunity.id),
        "title": opportunity.title,
        "organization": organization.canonical_name if organization else None,
        "type": opportunity.opportunity_type.value,
        "score": assessment.score_total if assessment else None,
        "bucket": bucket.value,
        "hard_gate": hard_gate,
        "confidence": assessment.confidence if assessment else None,
        "professional_eligibility": opportunity.professional_eligibility.value,
        "india_eligibility": opportunity.india_eligibility.value,
        "student_only": opportunity.student_only,
        "deadline_on": opportunity.deadline_on.isoformat() if opportunity.deadline_on else None,
        "deadline_at": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None,
        "deadline_precision": opportunity.deadline_precision.value,
        "deadline_label": _deadline_label(opportunity),
        "days_until_deadline": days_until(opportunity.deadline_at or opportunity.deadline_on),
        "official_url": _safe_url(opportunity.official_url),
        "credibility": opportunity.credibility_level.value,
        "life_state": opportunity.life_state.value,
        "why": assessment.recommendation_reason if assessment else None,
        "next_action": _next_action(bucket, hard_gate),
        "last_verified_at": opportunity.last_verified_at.isoformat()
        if opportunity.last_verified_at
        else None,
    }


def _markdown_item(index: int, item: dict) -> list[str]:
    title = _escape_markdown(item["title"], 240)
    organization = _escape_markdown(item["organization"] or "Unknown organization", 200)
    score = f"{item['score']}/100" if item["score"] is not None else "unscored"
    lines = [
        f"{index}. **{title}** - {organization} ({score}, {item['bucket']})",
        f"   - Eligibility: professional `{item['professional_eligibility']}`; "
        f"India `{item['india_eligibility']}`",
        f"   - Deadline: {_escape_markdown(item['deadline_label'], 200)}",
    ]
    if item["official_url"]:
        lines.append(f"   - Source: <{item['official_url']}>")
    if item["why"]:
        lines.append(f"   - Why relevant: {_escape_markdown(item['why'], 600)}")
    if item["last_verified_at"]:
        lines.append(f"   - Last verified: {item['last_verified_at']}")
    lines.append(f"   - Next action: {_escape_markdown(item['next_action'], 300)}")
    return lines


def _render_markdown(payload: dict, kind: DigestKind) -> str:
    label = "Daily" if kind == DigestKind.daily else "Weekly"
    lines = [
        f"# DiscMon {label} Brief",
        "",
        f"Period: {payload['period_start']} to {payload['period_end']} (UTC)",
        f"Generated: {payload['generated_at']}",
        "",
        "All eligibility and deadlines must be re-verified on the official source. "
        "Unknown is not yes.",
        "",
        "## Top finds",
    ]
    if payload["top_finds"]:
        for index, item in enumerate(payload["top_finds"], start=1):
            lines.extend(_markdown_item(index, item))
            lines.append("")
    else:
        lines.extend(["No scored opportunities in this window.", ""])

    lines.append("## Closing soon")
    if payload["closing_soon"]:
        for index, item in enumerate(payload["closing_soon"], start=1):
            lines.extend(_markdown_item(index, item))
            lines.append("")
    else:
        lines.extend(["No published deadlines within 30 days.", ""])

    lines.append("## Preparation signals")
    if payload["prepare_early"]:
        for index, item in enumerate(payload["prepare_early"], start=1):
            lines.extend(_markdown_item(index, item))
            lines.append("")
    else:
        lines.extend(["No early-preparation items in this window.", ""])

    lines.append("## Needs verification")
    if payload["needs_verification"]:
        for index, item in enumerate(payload["needs_verification"], start=1):
            lines.extend(_markdown_item(index, item))
            lines.append("")
    else:
        lines.extend(["No unresolved eligibility or deadline items.", ""])

    health = payload["source_health"]
    lines.extend(
        [
            "## Source health",
            f"- Healthy: {health['counts'].get('healthy', 0)}",
            f"- Stale: {health['counts'].get('stale', 0)}",
            f"- Failing: {health['counts'].get('failing', 0)}",
            f"- Unknown: {health['counts'].get('unknown', 0)}",
        ]
    )
    if health["attention"]:
        lines.append("- Needs attention: " + ", ".join(health["attention"]))
    else:
        lines.append("- No failing sources reported.")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


async def collect_digest_payload(
    session: AsyncSession,
    kind: DigestKind,
    reference: datetime | None = None,
) -> dict:
    period_start, period_end = digest_window(kind, reference)
    now = reference or now_utc()
    latest = _latest_assessment_id()
    rows = (
        await session.execute(
            select(Opportunity, Organization, Assessment)
            .outerjoin(Organization, Organization.id == Opportunity.organization_id)
            .outerjoin(Assessment, Assessment.id == latest)
            .where(
                Opportunity.is_fixture.is_(False),
                Opportunity.life_state.in_([LifeState.open, LifeState.upcoming]),
                Opportunity.user_decision.notin_(
                    [UserDecision.ignored, UserDecision.completed, UserDecision.rejected]
                ),
            )
            .limit(1000)
        )
    ).all()

    items: list[dict] = []
    for opportunity, organization, assessment in rows:
        if assessment is not None and assessment.recommended_bucket in {
            RecommendationBucket.excluded,
            RecommendationBucket.archive,
        }:
            continue
        items.append(_item(opportunity, organization, assessment))

    top_finds = sorted(
        items,
        key=lambda item: (item["score"] is not None, item["score"] or 0),
        reverse=True,
    )[:TOP_FIND_LIMIT]

    closing_soon = sorted(
        (
            item
            for item in items
            if item["days_until_deadline"] is not None and 0 <= item["days_until_deadline"] <= 30
        ),
        key=lambda item: (item["days_until_deadline"], -(item["score"] or 0)),
    )[:SECTION_LIMIT]

    prepare_early = [
        item for item in items if item["bucket"] == RecommendationBucket.prepare_early.value
    ][:SECTION_LIMIT]

    needs_verification = [
        item
        for item in items
        if item["hard_gate"] == "needs_verification"
        or item["bucket"] == RecommendationBucket.needs_verification.value
        or item["professional_eligibility"] == EligibilityStatus.unknown.value
        or item["india_eligibility"] == EligibilityStatus.unknown.value
    ][:SECTION_LIMIT]

    health_rows = (
        await session.execute(
            select(Source.health_status, func.count(Source.id)).group_by(Source.health_status)
        )
    ).all()
    health_counts = {status.value: count for status, count in health_rows}
    attention_rows = (
        (
            await session.execute(
                select(Source.name)
                .where(
                    Source.health_status.in_([HealthStatus.stale, HealthStatus.failing]),
                    Source.enabled.is_(True),
                )
                .order_by(Source.health_status, Source.name)
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    payload = {
        "kind": kind.value,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": now.isoformat(),
        "top_finds": top_finds,
        "closing_soon": closing_soon,
        "prepare_early": prepare_early,
        "needs_verification": needs_verification,
        "source_health": {
            "counts": health_counts,
            "attention": [_escape_markdown(name, 200) for name in attention_rows],
        },
    }
    opportunity_ids = {
        item["id"] for item in top_finds + closing_soon + prepare_early + needs_verification
    }
    payload["opportunity_ids"] = sorted(opportunity_ids)
    return payload


async def generate_digest(
    session: AsyncSession,
    kind: DigestKind,
    reference: datetime | None = None,
) -> tuple[Digest, bool]:
    period_start, period_end = digest_window(kind, reference)
    existing = await session.scalar(
        select(Digest).where(
            Digest.period_start == period_start,
            Digest.period_end == period_end,
            Digest.digest_kind == kind,
        )
    )
    if existing is not None and existing.sent_status != "demo":
        return existing, False
    if existing is not None:
        await session.delete(existing)
        await session.flush()
    payload = await collect_digest_payload(session, kind, reference)
    content_md = _render_markdown(payload, kind)
    digest = Digest(
        period_start=period_start,
        period_end=period_end,
        digest_kind=kind,
        generated_at=reference or now_utc(),
        content_md=content_md,
        content_json=payload,
        opportunity_ids=payload["opportunity_ids"],
        sent_status="generated",
    )
    session.add(digest)
    await session.flush()
    return digest, True


async def current_brief_markdown(
    session: AsyncSession,
    kind: DigestKind = DigestKind.weekly,
    reference: datetime | None = None,
) -> str:
    payload = await collect_digest_payload(session, kind, reference)
    return _render_markdown(payload, kind)


def iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None
