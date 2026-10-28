from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import SyncStatus
from app.db.models.sync import SyncOutbox, SyncState
from app.services import ingestion, sheets
from tests.factories import FakeAdapter, make_candidate, make_source


class FakeSheetsGateway:
    instances: list[FakeSheetsGateway] = []

    def __init__(self) -> None:
        self.rows_data: list[list[object]] = []
        self.header_written = False
        self.appended: list[list[str]] = []
        self.updated: list[tuple[int, list[str]]] = []
        self.closed = False
        FakeSheetsGateway.instances.append(self)

    @classmethod
    async def create(cls, settings):
        return cls()

    async def close(self) -> None:
        self.closed = True

    async def rows(self) -> list[list[object]]:
        return self.rows_data

    async def write_header(self) -> None:
        self.header_written = True

    async def update_row(self, row_number: int, values: list[str]) -> None:
        self.updated.append((row_number, values))

    async def append_row(self, values: list[str]) -> int:
        self.appended.append(values)
        return len(self.appended) + 1


@pytest.mark.integration
async def test_sheets_outbox_syncs_and_updates_existing_row(
    session: AsyncSession, monkeypatch
) -> None:
    settings = SimpleNamespace(
        sheets_sync_enabled=True,
        sheets_configured=True,
        google_sheets_spreadsheet_id="sheet-123",
        google_sheets_tab="Opportunities",
    )
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)
    monkeypatch.setattr(sheets, "SheetsGateway", FakeSheetsGateway)
    FakeSheetsGateway.instances.clear()

    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 1

    outbox_rows = (await session.execute(select(SyncOutbox))).scalars().all()
    assert len(outbox_rows) == 1
    assert outbox_rows[0].status == SyncStatus.pending

    result = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert result["synced"] == 1
    gateway = FakeSheetsGateway.instances[0]
    assert gateway.header_written is True
    assert len(gateway.appended) == 1
    assert gateway.appended[0][1] == "Senior Backend Engineer"
    assert outbox_rows[0].status == SyncStatus.synced
    state = await session.scalar(select(SyncState))
    assert state is not None
    assert state.last_success_at is not None

    result = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert result["synced"] == 0

    opportunity_id = outbox_rows[0].entity_id
    created = await sheets.enqueue_sheet_upsert(session, opportunity_id)
    assert created is not None
    await session.commit()

    second_gateway = FakeSheetsGateway()
    second_gateway.rows_data = [
        sheets.SHEET_HEADERS,
        [str(opportunity_id), "Senior Backend Engineer"],
    ]

    async def create_fake(cls, settings):
        return second_gateway

    monkeypatch.setattr(FakeSheetsGateway, "create", classmethod(create_fake))
    result = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert result["synced"] == 1
    assert second_gateway.appended == []
    assert second_gateway.updated[0][0] == 2
    assert second_gateway.updated[0][1][0] == str(opportunity_id)
    assert second_gateway.closed is True


@pytest.mark.integration
async def test_sheets_disabled_does_not_accumulate_outbox(
    session: AsyncSession, monkeypatch
) -> None:
    settings = SimpleNamespace(
        sheets_sync_enabled=False,
        sheets_configured=False,
        google_sheets_spreadsheet_id=None,
        google_sheets_tab="Opportunities",
    )
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 1
    assert (await session.execute(select(SyncOutbox))).scalars().all() == []
    result = await sheets.process_sheets_outbox(session)
    assert result["enabled"] is False
