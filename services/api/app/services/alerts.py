from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.enums import AlertKind, AlertStatus, EligibilityStatus
from app.db.models.opportunity import Opportunity, OpportunityRevision
from app.db.models.user import UserProfile
from app.services.time import days_until, is_within_quiet_hours, next_allowed_slot, now_utc

IMMEDIATE_SCORE = 85
DEADLINE_SCORE = 75


def eligible_for_immediate(
    opportunity: Opportunity, assessment: Assessment, reference: datetime | None = None
) -> bool:
    verified = opportunity.professional_eligibility in {
        EligibilityStatus.verified_yes,
        EligibilityStatus.not_applicable,
    } and opportunity.india_eligibility in {
        EligibilityStatus.verified_yes,
        EligibilityStatus.not_applicable,
    }
    credible = opportunity.credibility_level.value in {"high", "medium"}
    if not (verified and credible):
        return False
    if assessment.score_total >= IMMEDIATE_SCORE:
        return True
    remaining = days_until(opportunity.deadline_at or opportunity.deadline_on)
    return (
        remaining is not None and 0 <= remaining <= 7 and assessment.score_total >= DEADLINE_SCORE
    )


def _payload(
    opportunity: Opportunity,
    assessment: Assessment,
    revision: OpportunityRevision | None,
    organization_name: str | None = None,
) -> dict:
    return {
        "opportunity_id": str(opportunity.id),
        "title": opportunity.title,
        "organization": organization_name,
        "score": assessment.score_total,
        "bucket": assessment.recommended_bucket.value,
        "professional_eligibility": opportunity.professional_eligibility.value,
        "india_eligibility": opportunity.india_eligibility.value,
        "deadline_on": opportunity.deadline_on.isoformat() if opportunity.deadline_on else None,
        "deadline_at": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None,
        "deadline_precision": opportunity.deadline_precision.value,
        "official_url": opportunity.official_url,
        "why": assessment.recommendation_reason,
        "revision_id": str(revision.id) if revision else None,
        "revision_type": revision.revision_type.value if revision else None,
        "material_diff": revision.material_diff_json if revision else {},
        "evidence": assessment.evidence_refs_json[:3],
    }


async def maybe_create_alerts(
    session: AsyncSession,
    opportunity: Opportunity,
    assessment: Assessment,
    revision: OpportunityRevision | None,
    profile: UserProfile,
    organization_name: str | None = None,
) -> list[Alert]:
    if revision is None or not eligible_for_immediate(opportunity, assessment):
        return []
    if revision.revision_type.value not in {"created", "updated", "reopened"}:
        return []
    now = now_utc()
    scheduled_for = now
    if is_within_quiet_hours(
        now, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
    ):
        scheduled_for = next_allowed_slot(
            now, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
        )
    channels = profile.alert_channels or ["in_app"]
    created: list[Alert] = []
    for channel in channels:
        dedup = f"opp:{opportunity.id}:rev:{revision.id}:{channel}:immediate"
        existing = await session.scalar(select(Alert).where(Alert.dedup_key == dedup))
        if existing is not None:
            continue
        alert = Alert(
            opportunity_id=opportunity.id,
            revision_id=revision.id,
            channel=channel,
            alert_kind=AlertKind.immediate,
            dedup_key=dedup,
            status=AlertStatus.pending,
            payload_json=_payload(opportunity, assessment, revision, organization_name),
            scheduled_for=scheduled_for,
        )
        session.add(alert)
        created.append(alert)
    await session.flush()
    return created


async def deliver_pending_alerts(session: AsyncSession, limit: int = 50) -> dict:
    settings = get_settings()
    now = now_utc()
    alerts = (
        (
            await session.execute(
                select(Alert)
                .where(
                    Alert.status == AlertStatus.pending,
                    Alert.scheduled_for <= now,
                )
                .order_by(Alert.scheduled_for)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    failed = 0
    for alert in alerts:
        if alert.channel == "in_app":
            alert.status = AlertStatus.sent
            alert.sent_at = now
            sent += 1
            continue
        if alert.channel == "telegram":
            if not settings.telegram_enabled:
                alert.last_error_redacted = (
                    "Telegram is not configured; alert remains in in-app inbox"
                )
                failed += 1
                continue
            try:
                message = _telegram_text(alert.payload_json)
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(
                        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                        json={
                            "chat_id": settings.telegram_allowed_chat_id,
                            "text": message,
                            "disable_web_page_preview": True,
                        },
                    )
                response.raise_for_status()
                alert.status = AlertStatus.sent
                alert.sent_at = now
                alert.provider_message_id = str(response.json().get("result", {}).get("message_id"))
                sent += 1
            except Exception:
                alert.retry_count += 1
                alert.last_error_redacted = "Telegram delivery failed; see server logs"
                alert.status = AlertStatus.failed if alert.retry_count >= 4 else AlertStatus.pending
                failed += 1
            continue
        alert.status = AlertStatus.failed
        alert.last_error_redacted = f"Unsupported channel: {alert.channel}"
        failed += 1
    await session.flush()
    return {"sent": sent, "failed": failed, "processed": len(alerts)}


def _telegram_text(payload: dict) -> str:
    lines = [
        f"DiscMon: {payload.get('title') or 'Opportunity'}",
        f"Organization: {payload.get('organization') or 'Unknown'}",
        f"Score: {payload.get('score')}/100 · {payload.get('bucket')}",
        f"Professional eligibility: {payload.get('professional_eligibility')}",
        f"India eligibility: {payload.get('india_eligibility')}",
    ]
    if payload.get("deadline_on"):
        lines.append(f"Deadline: {payload['deadline_on']} ({payload.get('deadline_precision')})")
    lines.append(str(payload.get("official_url") or ""))
    lines.append("Verify live details before acting.")
    return "\n".join(lines)[:4000]
