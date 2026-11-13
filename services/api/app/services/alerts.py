from __future__ import annotations

import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

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
    # Dispatch owns its transaction: Telegram claims commit before external I/O.
    settings = get_settings()
    now = now_utc()
    alert_ids = (
        (
            await session.execute(
                select(Alert.id)
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
    processed = 0
    for alert_id in alert_ids:
        alert = await session.scalar(
            select(Alert)
            .where(Alert.id == alert_id, Alert.status == AlertStatus.pending)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if alert is None:
            continue
        processed += 1
        if alert.channel == "in_app":
            alert.status = AlertStatus.sent
            alert.sent_at = now
            sent += 1
            continue
        if alert.channel in {"email", "smtp"}:
            if not settings.smtp_enabled:
                alert.last_error_redacted = "SMTP is not configured; alert remains in in-app inbox"
                failed += 1
                continue
            try:
                subject, message = _email_text(alert.payload_json)
                await asyncio.to_thread(_send_smtp, subject, message)
                alert.status = AlertStatus.sent
                alert.sent_at = now
                alert.provider_message_id = make_msgid(domain="discmon.local")
                sent += 1
            except Exception:
                alert.retry_count += 1
                alert.last_error_redacted = "SMTP delivery failed; see server logs"
                alert.status = AlertStatus.failed if alert.retry_count >= 4 else AlertStatus.pending
                failed += 1
            continue
        if alert.channel == "telegram":
            profile = await session.scalar(
                select(UserProfile)
                .order_by(UserProfile.created_at)
                .limit(1)
                .execution_options(populate_existing=True)
            )
            if profile is None or "telegram" not in (profile.alert_channels or []):
                alert.status = AlertStatus.suppressed
                alert.last_error_redacted = (
                    "Telegram consent revoked or absent; delivery suppressed"
                )
                continue
            if not settings.telegram_enabled:
                alert.last_error_redacted = (
                    "Telegram is not configured; alert remains in in-app inbox"
                )
                failed += 1
                continue
            if is_within_quiet_hours(
                now, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
            ):
                alert.scheduled_for = next_allowed_slot(
                    now, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
                )
                continue
            # A committed terminal claim prevents replay even if the process dies mid-send.
            alert.status = AlertStatus.failed
            alert.retry_count += 1
            alert.last_error_redacted = (
                "Telegram outcome unconfirmed; manual review required; do not automatically retry"
            )
            await session.commit()
            profile = await session.scalar(
                select(UserProfile)
                .order_by(UserProfile.created_at)
                .limit(1)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if profile is None or "telegram" not in (profile.alert_channels or []):
                alert.status = AlertStatus.suppressed
                alert.last_error_redacted = "Telegram consent revoked; delivery suppressed"
                continue
            current = now_utc()
            if is_within_quiet_hours(
                current, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
            ):
                alert.status = AlertStatus.pending
                alert.scheduled_for = next_allowed_slot(
                    current, profile.quiet_hours_start, profile.quiet_hours_end, profile.timezone
                )
                alert.last_error_redacted = None
                continue
            try:
                request = httpx.Request(
                    "POST",
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": settings.telegram_allowed_chat_id,
                        "text": _telegram_text(alert.payload_json),
                        "disable_web_page_preview": True,
                    },
                    extensions={"timeout": httpx.Timeout(15).as_dict()},
                )
                # Avoid AsyncClient's INFO log of the credential-bearing request URL.
                async with httpx.AsyncHTTPTransport() as transport:
                    response = await transport.handle_async_request(request)
                    try:
                        await response.aread()
                    finally:
                        await response.aclose()
                if response.status_code in {401, 403}:
                    alert.last_error_redacted = (
                        "Telegram authorization rejected; review configuration"
                    )
                elif response.status_code == 429:
                    alert.last_error_redacted = (
                        "Telegram rate limited; review provider backoff before manual retry"
                    )
                elif response.status_code == 200:
                    body = response.json()
                    if isinstance(body, dict) and body.get("ok") is False:
                        _telegram_rejected(alert, "Telegram rejected request")
                    elif _telegram_acknowledged(body, settings.telegram_allowed_chat_id):
                        alert.status = AlertStatus.sent
                        alert.sent_at = now_utc()
                        alert.provider_message_id = str(body["result"]["message_id"])
                        alert.last_error_redacted = None
                        sent += 1
                        continue
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                _telegram_rejected(alert, "Telegram connection unavailable before dispatch")
            except Exception:
                # Never include exception text, URLs, destinations or provider bodies.
                pass
            failed += 1
            continue
        alert.status = AlertStatus.failed
        alert.last_error_redacted = f"Unsupported channel: {alert.channel}"
        failed += 1
    await session.flush()
    return {"sent": sent, "failed": failed, "processed": processed}


def _telegram_rejected(alert: Alert, message: str) -> None:
    alert.status = AlertStatus.failed if alert.retry_count >= 4 else AlertStatus.pending
    alert.last_error_redacted = message


def _telegram_acknowledged(body: object, chat_id: str | None) -> bool:
    if not isinstance(body, dict) or body.get("ok") is not True:
        return False
    result = body.get("result")
    if not isinstance(result, dict):
        return False
    message_id = result.get("message_id")
    chat = result.get("chat")
    return (
        type(message_id) is int
        and message_id > 0
        and isinstance(chat, dict)
        and type(chat.get("id")) is int
        and str(chat["id"]) == chat_id
    )


def _send_smtp(subject: str, message: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from or not settings.smtp_to:
        raise RuntimeError("SMTP is not configured")
    sender = EmailMessage()
    sender["Subject"] = subject[:180].replace("\r", " ").replace("\n", " ")
    sender["From"] = formataddr(("DiscMon", settings.smtp_from))
    sender["To"] = settings.smtp_to
    sender["Message-ID"] = make_msgid(domain="discmon.local")
    sender.set_content(message)
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(sender)
        return
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password or "")
        smtp.send_message(sender)


def _email_text(payload: dict) -> tuple[str, str]:
    title = str(payload.get("title") or "Opportunity").replace("\r", " ").replace("\n", " ")
    subject = f"DiscMon alert: {title}"[:180]
    lines = _telegram_text(payload).splitlines()
    opportunity_id = payload.get("opportunity_id")
    if opportunity_id:
        settings = get_settings()
        lines.append(
            f"Open in DiscMon: {settings.app_base_url.rstrip('/')}/opportunities/{opportunity_id}"
        )
    return subject, "\n".join(lines)


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
