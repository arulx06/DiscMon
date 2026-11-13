from __future__ import annotations

import hmac
import re
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_owner
from app.config import get_settings
from app.db.models.runtime_schedule import RuntimeSchedule
from app.db.session import get_db

TIMEZONE = "Asia/Kolkata"
STALE_AFTER = timedelta(minutes=3)
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

owner_router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])
host_router = APIRouter(prefix="/runtime-sync")


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    start_time: str
    shutdown_time: str

    @field_validator("start_time", "shutdown_time")
    @classmethod
    def strict_clock_time(cls, value: str) -> str:
        if not _TIME_PATTERN.fullmatch(value):
            raise ValueError("Time must use strict 24-hour HH:MM format")
        return value


class HostScheduleAck(ScheduleUpdate):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def fixed_timezone(cls, value: str) -> str:
        if value != TIMEZONE:
            raise ValueError(f"Timezone must be {TIMEZONE}")
        return value


def _validate_window(start_time: str, shutdown_time: str) -> tuple[time, time]:
    start = time.fromisoformat(start_time)
    shutdown = time.fromisoformat(shutdown_time)
    if start >= shutdown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Start time must be earlier than shutdown time on the same day",
        )
    duration = datetime.combine(datetime.min, shutdown) - datetime.combine(datetime.min, start)
    if duration < timedelta(minutes=60):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Runtime schedule must be at least 60 minutes",
        )
    if start > time(20, 0) or shutdown < time(21, 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "This schedule is incompatible with the existing 20:30 backup timer; "
                "start must be no later than 20:00 and shutdown no earlier than 21:00. "
                "Earlier shutdown times are unsupported until the backup schedule is migrated."
            ),
        )
    return start, shutdown


def _time_string(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def _owner_view(schedule: RuntimeSchedule) -> dict:
    now = datetime.now(UTC)
    if schedule.sync_error:
        sync_status = "error"
    elif schedule.applied_revision is None:
        sync_status = "pending"
    elif schedule.applied_revision != schedule.revision:
        sync_status = "pending"
    elif schedule.last_sync_at is None or now - schedule.last_sync_at > STALE_AFTER:
        sync_status = "stale"
    else:
        sync_status = "applied"
    start = _time_string(schedule.start_time)
    shutdown = _time_string(schedule.shutdown_time)
    assert start is not None and shutdown is not None
    duration = (
        datetime.combine(datetime.min, schedule.shutdown_time)
        - datetime.combine(datetime.min, schedule.start_time)
    ).seconds // 60
    return {
        "revision": schedule.revision,
        "start_time": start,
        "shutdown_time": shutdown,
        "timezone": schedule.timezone,
        "applied_revision": schedule.applied_revision,
        "applied_start_time": _time_string(schedule.applied_start_time),
        "applied_shutdown_time": _time_string(schedule.applied_shutdown_time),
        "last_sync_at": schedule.last_sync_at,
        "sync_error": schedule.sync_error,
        "status": sync_status,
        "duration_minutes": duration,
    }


async def _locked_schedule(session: AsyncSession) -> RuntimeSchedule:
    schedule = await session.scalar(
        select(RuntimeSchedule).where(RuntimeSchedule.id == 1).with_for_update()
    )
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime schedule is not initialized; apply the database migration",
        )
    return schedule


async def _host_authorized(
    authorization: str | None = Header(default=None),
) -> None:
    expected = get_settings().runtime_sync_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Host runtime synchronization is disabled",
        )
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Host runtime synchronization authentication required",
        )


@owner_router.get("/runtime-schedule")
async def get_runtime_schedule(session: AsyncSession = Depends(get_db)) -> dict:
    schedule = await session.get(RuntimeSchedule, 1)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime schedule is not initialized; apply the database migration",
        )
    return _owner_view(schedule)


@owner_router.put("/runtime-schedule")
async def put_runtime_schedule(
    body: ScheduleUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    start, shutdown = _validate_window(body.start_time, body.shutdown_time)
    schedule = await _locked_schedule(session)
    if schedule.revision != body.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Runtime schedule revision has changed; reload before saving",
        )
    schedule.revision += 1
    schedule.start_time = start
    schedule.shutdown_time = shutdown
    schedule.sync_error = None
    await session.commit()
    await session.refresh(schedule)
    return _owner_view(schedule)


@host_router.get("/schedule", dependencies=[Depends(_host_authorized)])
async def host_get_runtime_schedule(session: AsyncSession = Depends(get_db)) -> dict:
    schedule = await session.get(RuntimeSchedule, 1)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime schedule is not initialized; apply the database migration",
        )
    return {
        "revision": schedule.revision,
        "start_time": _time_string(schedule.start_time),
        "shutdown_time": _time_string(schedule.shutdown_time),
        "timezone": schedule.timezone,
    }


@host_router.post("/ack", dependencies=[Depends(_host_authorized)])
async def host_ack_runtime_schedule(
    body: HostScheduleAck,
    session: AsyncSession = Depends(get_db),
) -> dict:
    schedule = await _locked_schedule(session)
    if (
        body.revision != schedule.revision
        or body.start_time != _time_string(schedule.start_time)
        or body.shutdown_time != _time_string(schedule.shutdown_time)
        or body.timezone != schedule.timezone
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Runtime schedule changed before host application was acknowledged",
        )
    schedule.applied_revision = schedule.revision
    schedule.applied_start_time = schedule.start_time
    schedule.applied_shutdown_time = schedule.shutdown_time
    schedule.last_sync_at = datetime.now(UTC)
    schedule.sync_error = None
    await session.commit()
    return {"revision": schedule.revision, "acknowledged": True}
