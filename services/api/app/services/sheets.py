from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from urllib.parse import quote

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.assessment import Assessment
from app.db.models.enums import SyncStatus
from app.db.models.opportunity import Opportunity, Organization
from app.db.models.review import Review
from app.db.models.sync import SyncOutbox, SyncState
from app.services.time import now_utc

SHEET_HEADERS = [
    "Opportunity ID",
    "Title",
    "Organization",
    "Type",
    "Decision",
    "Bucket",
    "Score",
    "Professional Eligibility",
    "India Eligibility",
    "Location",
    "Workplace",
    "Deadline",
    "Deadline Precision",
    "Official URL",
    "Next Action",
    "Follow-up Due",
    "Last Seen",
]
SHEET_RANGE = "A:Q"
LAST_COLUMN = "Q"
MAX_SYNC_ATTEMPTS = 5
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsConfigurationError(RuntimeError):
    pass


def _sheet_row_lookup(rows: object) -> dict[str, int]:
    if not isinstance(rows, list):
        raise SheetsConfigurationError("Invalid Google Sheets rows")
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) > len(SHEET_HEADERS)
            or any(not isinstance(cell, (str, int, float, bool)) for cell in row)
        ):
            raise SheetsConfigurationError("Invalid Google Sheets row")
    if not rows:
        return {}
    if rows[0] != SHEET_HEADERS:
        raise SheetsConfigurationError("Incompatible Google Sheets header")
    lookup: dict[str, int] = {}
    for index, row in enumerate(rows[1:], start=2):
        if not row or row[0] == "":
            continue
        identifier = row[0]
        if not isinstance(identifier, str) or identifier in lookup:
            raise SheetsConfigurationError("Invalid or duplicate Google Sheets opportunity ID")
        lookup[identifier] = index
    return lookup


class SheetsGateway:
    def __init__(self, settings: Settings, token: str, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.token = token
        self.client = client
        self.base_url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{quote(settings.google_sheets_spreadsheet_id or '', safe='')}/values"
        )
        self.tab = settings.google_sheets_tab.replace("'", "")

    @classmethod
    async def create(cls, settings: Settings) -> SheetsGateway:
        if not settings.sheets_configured:
            raise SheetsConfigurationError("Google Sheets credentials are incomplete")
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        credentials = await asyncio.to_thread(
            service_account.Credentials.from_service_account_file,
            settings.google_service_account_json_path,
            scopes=SCOPES,
        )
        await asyncio.to_thread(credentials.refresh, Request())
        if not credentials.token:
            raise SheetsConfigurationError("Google Sheets credentials could not refresh")
        client = httpx.AsyncClient(timeout=30)
        return cls(settings, str(credentials.token), client)

    async def close(self) -> None:
        await self.client.aclose()

    def _url(self, range_suffix: str) -> str:
        return f"{self.base_url}/{quote(range_suffix, safe='!:')}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def rows(self) -> list[list[object]]:
        # Content beyond Q must not make an unknown layout look empty.
        response = await self.client.get(
            self._url(f"'{self.tab}'"),
            headers=self._headers,
            params={"majorDimension": "ROWS"},
        )
        if response.status_code == 404:
            raise SheetsConfigurationError("Google Sheets spreadsheet was not found")
        response.raise_for_status()
        payload = response.json()
        if (
            not isinstance(payload, dict)
            or payload.keys() - {"range", "majorDimension", "values"}
            or ("range" in payload and not isinstance(payload["range"], str))
            or payload.get("majorDimension", "ROWS") != "ROWS"
        ):
            raise SheetsConfigurationError("Invalid Google Sheets response")
        values = payload.get("values", [])
        _sheet_row_lookup(values)
        return values

    async def write_header(self) -> None:
        response = await self.client.put(
            self._url(f"{self.tab}!A1:{LAST_COLUMN}1"),
            headers=self._headers,
            params={"valueInputOption": "RAW"},
            json={"values": [SHEET_HEADERS]},
        )
        response.raise_for_status()

    async def update_row(self, row_number: int, values: list[str]) -> None:
        response = await self.client.put(
            self._url(f"{self.tab}!A{row_number}:{LAST_COLUMN}{row_number}"),
            headers=self._headers,
            params={"valueInputOption": "RAW"},
            json={"values": [values]},
        )
        response.raise_for_status()

    async def append_row(self, values: list[str]) -> int | None:
        response = await self.client.post(
            self._url(f"{self.tab}!{SHEET_RANGE}:append"),
            headers=self._headers,
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"values": [values]},
        )
        response.raise_for_status()
        updates = response.json().get("updates") or {}
        updated_range = str(updates.get("updatedRange") or "")
        match = re.search(r"![A-Z]+(\d+)", updated_range)
        return int(match.group(1)) if match else None


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.replace("\x00", "")[:50_000]
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _deadline_text(opportunity: Opportunity) -> str:
    if opportunity.deadline_at is not None:
        return opportunity.deadline_at.isoformat()
    if opportunity.deadline_on is not None:
        return opportunity.deadline_on.isoformat()
    return ""


async def _row_values(session: AsyncSession, opportunity: Opportunity) -> list[str]:
    organization = (
        await session.get(Organization, opportunity.organization_id)
        if opportunity.organization_id
        else None
    )
    assessment = await session.scalar(
        select(Assessment)
        .where(Assessment.opportunity_id == opportunity.id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    )
    review = await session.scalar(
        select(Review)
        .where(Review.opportunity_id == opportunity.id)
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    return [
        _cell(str(opportunity.id)),
        _cell(opportunity.title),
        _cell(organization.canonical_name if organization else ""),
        _cell(opportunity.opportunity_type.value),
        _cell(opportunity.user_decision.value),
        _cell(assessment.recommended_bucket.value if assessment else "needs_verification"),
        _cell(assessment.score_total if assessment else ""),
        _cell(opportunity.professional_eligibility.value),
        _cell(opportunity.india_eligibility.value),
        _cell(opportunity.location_text),
        _cell(opportunity.workplace_type),
        _cell(_deadline_text(opportunity)),
        _cell(opportunity.deadline_precision.value),
        _cell(opportunity.official_url),
        _cell(opportunity.next_action),
        _cell(review.followup_due_at if review else None),
        _cell(opportunity.last_seen_at),
    ]


async def enqueue_sheet_upsert(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> uuid.UUID | None:
    settings = get_settings()
    if not settings.sheets_sync_enabled:
        return None
    existing = await session.scalar(
        select(SyncOutbox)
        .where(
            SyncOutbox.entity_type == "opportunity",
            SyncOutbox.entity_id == opportunity_id,
            SyncOutbox.status.in_(
                [SyncStatus.pending, SyncStatus.in_progress, SyncStatus.failed]
            ),
        )
        .order_by(SyncOutbox.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        if existing.status == SyncStatus.in_progress:
            return existing.id
        existing.status = SyncStatus.pending
        existing.retries = 0
        existing.last_error = None
        existing.payload_json = {**(existing.payload_json or {}), "reason": "upsert"}
        await session.flush()
        return existing.id
    row = SyncOutbox(
        entity_type="opportunity",
        entity_id=opportunity_id,
        operation="upsert",
        payload_json={"reason": "upsert"},
        status=SyncStatus.pending,
    )
    session.add(row)
    await session.flush()
    return row.id


async def _record_sync_state(
    session: AsyncSession,
    settings: Settings,
    remote_row_key: str | None,
    error: str | None = None,
) -> None:
    state = await session.scalar(
        select(SyncState).where(
            SyncState.sheet_id == (settings.google_sheets_spreadsheet_id or ""),
            SyncState.tab == settings.google_sheets_tab,
        )
    )
    if state is None:
        state = SyncState(
            sheet_id=settings.google_sheets_spreadsheet_id or "",
            tab=settings.google_sheets_tab,
        )
        session.add(state)
    if error is None:
        state.remote_row_key = remote_row_key
        state.last_success_at = now_utc()
    await session.flush()
    state.last_error = error if error is not None else await _unresolved_sync_error(session)
    await session.flush()


async def _unresolved_sync_error(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            select(SyncOutbox.last_error)
            .where(
                SyncOutbox.entity_type == "opportunity",
                SyncOutbox.status == SyncStatus.failed,
            )
            .order_by(SyncOutbox.last_attempt_at.desc(), SyncOutbox.created_at.desc())
            .limit(1)
        )
    ).first()
    return (row[0] or "Google Sheets sync failed") if row is not None else None


async def _record_sync_failure(
    session: AsyncSession,
    settings: Settings,
    rows: Sequence[SyncOutbox],
    exc: Exception,
) -> None:
    # Exception text, URLs and response bodies can contain credentials.
    error = "Google Sheets sync failed"
    if isinstance(exc, httpx.HTTPStatusError):
        error += f" (HTTP {exc.response.status_code})"
    attempted_at = now_utc()
    for row in rows:
        row.status = SyncStatus.failed
        row.retries += 1
        row.last_attempt_at = attempted_at
        row.last_error = error
    await _record_sync_state(session, settings, None, error=error)


async def process_sheets_outbox(session: AsyncSession, limit: int = 25) -> dict:
    settings = get_settings()
    if not settings.sheets_sync_enabled:
        return {"enabled": False, "synced": 0, "failed": 0, "skipped": 0}
    if not settings.sheets_configured:
        return {
            "enabled": True,
            "configured": False,
            "synced": 0,
            "failed": 0,
            "skipped": 0,
        }
    rows = (
        (
            await session.execute(
                select(SyncOutbox)
                .where(
                    SyncOutbox.entity_type == "opportunity",
                    SyncOutbox.status.in_(
                        [SyncStatus.pending, SyncStatus.failed]
                    ),
                    SyncOutbox.retries < MAX_SYNC_ATTEMPTS,
                )
                .order_by(SyncOutbox.created_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    result = {
        "enabled": True,
        "configured": True,
        "synced": 0,
        "failed": 0,
        "skipped": 0,
    }
    if not rows:
        return result
    gateway = None
    try:
        try:
            gateway = await SheetsGateway.create(settings)
            remote_rows = await gateway.rows()
            row_lookup = _sheet_row_lookup(remote_rows)
            if not remote_rows:
                await gateway.write_header()
        except Exception as exc:
            await _record_sync_failure(session, settings, rows, exc)
            result["failed"] = len(rows)
            return result
        for outbox_row in rows:
            outbox_row.last_attempt_at = now_utc()
            opportunity = await session.get(Opportunity, outbox_row.entity_id)
            if opportunity is None:
                outbox_row.status = SyncStatus.failed
                outbox_row.retries += 1
                outbox_row.last_error = "Opportunity no longer exists"
                await _record_sync_state(
                    session, settings, None, error=outbox_row.last_error
                )
                result["skipped"] += 1
                continue
            try:
                values = await _row_values(session, opportunity)
                existing_row = row_lookup.get(str(opportunity.id))
                if existing_row is not None:
                    await gateway.update_row(existing_row, values)
                    remote_row_key = str(existing_row)
                else:
                    appended = await gateway.append_row(values)
                    if appended is not None:
                        row_lookup[str(opportunity.id)] = appended
                    remote_row_key = str(appended) if appended is not None else str(opportunity.id)
                outbox_row.status = SyncStatus.synced
                outbox_row.last_error = None
                await _record_sync_state(session, settings, remote_row_key)
                result["synced"] += 1
            except Exception as exc:
                await _record_sync_failure(session, settings, [outbox_row], exc)
                result["failed"] += 1
        await session.flush()
    finally:
        if gateway is not None:
            await gateway.close()
    return result


async def sheets_status(session: AsyncSession) -> dict:
    settings = get_settings()
    rows = (
        await session.execute(
            select(SyncOutbox.status, func.count())
            .where(SyncOutbox.entity_type == "opportunity")
            .group_by(SyncOutbox.status)
        )
    ).all()
    state = await session.scalar(
        select(SyncState).where(
            SyncState.sheet_id == (settings.google_sheets_spreadsheet_id or ""),
            SyncState.tab == settings.google_sheets_tab,
        )
    )
    return {
        "enabled": settings.sheets_sync_enabled,
        "configured": settings.sheets_configured,
        "tab": settings.google_sheets_tab,
        "counts": {status.value: count for status, count in rows},
        "last_success_at": (
            state.last_success_at.isoformat() if state and state.last_success_at else None
        ),
        "last_error": (
            await _unresolved_sync_error(session) or (state.last_error if state else None)
        ),
    }
