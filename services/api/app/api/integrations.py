from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_owner
from app.config import get_settings
from app.db.models.enums import JobKind
from app.db.models.opportunity import Opportunity
from app.db.session import get_db
from app.services.queue import enqueue_job
from app.services.sheets import enqueue_sheet_upsert, sheets_status
from app.services.time import now_utc

router = APIRouter(
    prefix="/v1/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_owner)],
)


@router.get("/status")
async def integration_status(session: AsyncSession = Depends(get_db)) -> dict:
    settings = get_settings()
    sheets = await sheets_status(session)
    return {
        "changedetection": {
            "enabled": settings.changedetection_enabled,
            "base_url_configured": bool(settings.changedetection_base_url),
            "webhook_configured": bool(settings.changedetection_webhook_secret),
        },
        "telegram": {"enabled": settings.telegram_enabled},
        "smtp": {
            "enabled": settings.smtp_enabled,
            "host_configured": bool(settings.smtp_host),
            "tls_port": settings.smtp_port,
        },
        "sheets": sheets,
        "ai": {"enabled": settings.ai_enabled, "provider": settings.llm_provider},
    }


@router.get("/sheets/status")
async def get_sheets_status(session: AsyncSession = Depends(get_db)) -> dict:
    return await sheets_status(session)


async def _new_sheets_job(session: AsyncSession) -> uuid.UUID:
    stamp = now_utc().strftime("%Y%m%d%H%M")
    return await enqueue_job(
        session,
        JobKind.sheets_sync,
        f"sheets-sync:manual:{stamp}",
    )


@router.post("/sheets/sync", status_code=202)
async def sync_sheets(session: AsyncSession = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.sheets_sync_enabled:
        raise HTTPException(status_code=400, detail="Google Sheets sync is disabled")
    if not settings.sheets_configured:
        raise HTTPException(status_code=400, detail="Google Sheets credentials are incomplete")
    job_id = await _new_sheets_job(session)
    await session.commit()
    return {"job_id": str(job_id)}


@router.post("/sheets/backfill", status_code=202)
async def backfill_sheets(session: AsyncSession = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.sheets_sync_enabled:
        raise HTTPException(status_code=400, detail="Google Sheets sync is disabled")
    if not settings.sheets_configured:
        raise HTTPException(status_code=400, detail="Google Sheets credentials are incomplete")
    opportunity_ids = (
        (await session.execute(select(Opportunity.id).order_by(Opportunity.created_at)))
        .scalars()
        .all()
    )
    queued = 0
    for opportunity_id in opportunity_ids:
        if await enqueue_sheet_upsert(session, opportunity_id) is not None:
            queued += 1
    job_id = await _new_sheets_job(session)
    await session.commit()
    return {"job_id": str(job_id), "opportunities_queued": queued}
