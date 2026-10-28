from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.enums import ApprovalStatus, LegalReviewStatus, SourceKind
from app.db.models.source import Source
from app.db.models.webhook import WebhookEvent
from app.db.session import get_db
from app.services.queue import enqueue_source_job

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])

MAX_WEBHOOK_BYTES = 64 * 1024
TIMESTAMP_TOLERANCE_SECONDS = 300


def _signature_valid(body: bytes, request: Request, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    supplied = request.headers.get("x-changedetection-signature", "").strip()
    if supplied:
        if supplied.lower().startswith("sha256="):
            supplied = supplied.split("=", 1)[1]
        return hmac.compare_digest(supplied.lower(), expected)
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        token = bearer[7:].strip()
        return hmac.compare_digest(token, secret)
    token = request.headers.get("x-changedetection-token", "").strip()
    return bool(token) and hmac.compare_digest(token, secret)


def _timestamp_valid(request: Request) -> bool:
    supplied = request.headers.get("x-changedetection-timestamp", "").strip()
    if not supplied:
        return True
    try:
        timestamp = int(supplied)
    except ValueError:
        try:
            timestamp = int(datetime.fromisoformat(supplied.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return False
    now = datetime.now(tz=UTC).timestamp()
    return abs(now - timestamp) <= TIMESTAMP_TOLERANCE_SECONDS


async def _match_source(session: AsyncSession, watch_uuid: str) -> Source | None:
    sources = (
        (
            await session.execute(
                select(Source).where(Source.source_kind == SourceKind.changedetection)
            )
        )
        .scalars()
        .all()
    )
    for source in sources:
        config = source.config_json or {}
        configured = str(config.get("watch_uuid") or "")
        if not configured or not hmac.compare_digest(configured, watch_uuid):
            continue
        if (
            not source.enabled
            or source.approval_status != ApprovalStatus.approved
            or source.legal_review_status != LegalReviewStatus.approved
        ):
            return None
        return source
    return None


@router.post("/changedetection/webhook", status_code=202)
async def changedetection_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.changedetection_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook is not configured")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BYTES:
                raise HTTPException(status_code=413, detail="Webhook body is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid content length") from exc
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body is too large")
    if not _signature_valid(body, request, settings.changedetection_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    if not _timestamp_valid(request):
        raise HTTPException(status_code=401, detail="Stale webhook timestamp")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")
    watch_uuid = str(payload.get("watch_uuid") or "").strip()
    watch_url = str(payload.get("watch_url") or "").strip() or None
    if not watch_uuid or len(watch_uuid) > 128:
        raise HTTPException(status_code=400, detail="Webhook is missing watch_uuid")
    if watch_url and len(watch_url) > 2048:
        raise HTTPException(status_code=400, detail="Webhook watch_url is too long")
    event_hash = hashlib.sha256(body).hexdigest()
    source = await _match_source(session, watch_uuid)

    event_id = await session.scalar(
        insert(WebhookEvent)
        .values(
            provider="changedetection",
            event_hash=event_hash,
            watch_uuid=watch_uuid,
            watch_url=watch_url,
            source_id=source.id if source is not None else None,
            status="received",
            detail_redacted=(
                None
                if source is not None
                else "No enabled approved source matches this watch_uuid"
            ),
        )
        .on_conflict_do_nothing(index_elements=[WebhookEvent.event_hash])
        .returning(WebhookEvent.id)
    )
    if event_id is None:
        await session.rollback()
        return {"status": "duplicate"}
    if source is None:
        await session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status="ignored")
        )
        await session.commit()
        return {"status": "ignored"}
    job_id = await enqueue_source_job(session, source.id)
    status = "queued" if job_id is not None else "already_queued"
    await session.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == event_id)
        .values(status=status, job_id=job_id)
    )
    await session.commit()
    return {"status": status}
