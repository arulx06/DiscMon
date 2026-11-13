from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment
from app.db.models.enums import SyncStatus, UserDecision
from app.db.models.opportunity import Opportunity
from app.db.models.review import Review
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


def _settings(*, enabled: bool = True, configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        sheets_sync_enabled=enabled,
        sheets_configured=configured,
        google_sheets_spreadsheet_id="test-sheet",
        google_sheets_tab="Opportunities",
        google_service_account_json_path="unused-test-credentials.json",
    )


async def _enqueue_opportunities(
    session: AsyncSession, monkeypatch, count: int = 1
) -> list[SyncOutbox]:
    monkeypatch.setattr(sheets, "get_settings", lambda: _settings())
    source = await make_source(session)
    adapter = FakeAdapter(
        [make_candidate(external_id=str(index)) for index in range(count)]
    )
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == count
    return list(
        (
            await session.scalars(
                select(SyncOutbox).order_by(SyncOutbox.created_at)
            )
        ).all()
    )


def _mock_gateway(
    monkeypatch, settings, handler
) -> tuple[sheets.SheetsGateway, list[httpx.Request], list[sheets.SheetsGateway]]:
    requests: list[httpx.Request] = []
    gateways: list[sheets.SheetsGateway] = []

    async def record_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return await handler(request)

    def new_gateway() -> sheets.SheetsGateway:
        gateway = sheets.SheetsGateway(
            settings,
            "dummy-sheets-token",
            httpx.AsyncClient(transport=httpx.MockTransport(record_request)),
        )
        gateways.append(gateway)
        return gateway

    gateway = new_gateway()

    async def create_gateway(cls, passed_settings):
        assert passed_settings is settings
        return gateway if not gateway.client.is_closed else new_gateway()

    monkeypatch.setattr(
        sheets.SheetsGateway, "create", classmethod(create_gateway)
    )
    return gateway, requests, gateways


async def _canonical_snapshot(session: AsyncSession, model) -> list[dict[str, object]]:
    records = (
        await session.scalars(
            select(model).order_by(model.id).execution_options(populate_existing=True)
        )
    ).all()
    return [
        {
            column.key: deepcopy(getattr(record, column.key))
            for column in model.__table__.columns
        }
        for record in records
    ]


def _assert_sanitized_sync_error(error: str | None, status: int | None = None) -> None:
    assert error is not None
    allowed = {"Google Sheets sync failed"}
    if status is not None:
        allowed.add(f"Google Sheets sync failed (HTTP {status})")
    assert error in allowed
    assert "dummy-sheets-token" not in error
    assert "synthetic" not in error.lower()


@pytest.mark.integration
@pytest.mark.parametrize("auth_failure", ["credential_load", "token_refresh"])
async def test_sheets_auth_failure_is_a_sanitized_retryable_outbox_failure(
    session: AsyncSession, monkeypatch, auth_failure: str
) -> None:
    from google.oauth2 import service_account

    outbox_rows = await _enqueue_opportunities(session, monkeypatch)
    settings = _settings()
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)

    class DummyCredentials:
        token = "dummy-sheets-token"

        def refresh(self, request) -> None:
            raise RuntimeError("refresh failed with private credential details")

    if auth_failure == "credential_load":
        def load_credentials(cls, filename, scopes):
            raise RuntimeError("credential file contains private details")

        monkeypatch.setattr(
            service_account.Credentials,
            "from_service_account_file",
            classmethod(load_credentials),
        )
    else:
        monkeypatch.setattr(
            service_account.Credentials,
            "from_service_account_file",
            classmethod(lambda cls, filename, scopes: DummyCredentials()),
        )

    result = await sheets.process_sheets_outbox(session)
    await session.commit()

    assert result["failed"] == 1
    assert result["synced"] == 0
    outbox = outbox_rows[0]
    assert outbox.status == SyncStatus.failed
    assert outbox.retries == 1
    assert outbox.last_attempt_at is not None
    _assert_sanitized_sync_error(outbox.last_error)
    status = await sheets.sheets_status(session)
    assert status["counts"][SyncStatus.failed.value] == 1
    _assert_sanitized_sync_error(status["last_error"])


@pytest.mark.integration
@pytest.mark.parametrize(
    ("failure", "http_status", "limit"),
    [
        ("http_403", 403, 2),
        ("http_429", 429, 1),
        ("http_503", 503, 1),
        ("connection", None, 1),
    ],
)
async def test_sheets_initial_read_failure_is_retryable_and_preserves_canonical_rows(
    session: AsyncSession, monkeypatch, failure: str, http_status: int | None, limit: int
) -> None:
    outbox_rows = await _enqueue_opportunities(session, monkeypatch, count=2)
    opportunity = (await session.scalars(select(Opportunity))).first()
    assert opportunity is not None
    review = Review(
        opportunity_id=opportunity.id,
        decision=UserDecision.unreviewed,
        note="Canonical test review",
    )
    session.add(review)
    await session.commit()
    before = {
        model: await _canonical_snapshot(session, model)
        for model in (Opportunity, Assessment, Review)
    }
    settings = _settings()
    prior_success = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    prior_row_key = "previous-successful-row"
    session.add(
        SyncState(
            sheet_id=settings.google_sheets_spreadsheet_id,
            tab=settings.google_sheets_tab,
            remote_row_key=prior_row_key,
            last_success_at=prior_success,
        )
    )
    await session.commit()

    async def fail_request(request: httpx.Request) -> httpx.Response:
        if failure == "connection":
            raise httpx.ConnectError("connection exposed private details", request=request)
        return httpx.Response(
            http_status or 500,
            text="remote error includes private response content",
            request=request,
        )

    gateway, requests, _ = _mock_gateway(monkeypatch, settings, fail_request)
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)
    result = await sheets.process_sheets_outbox(session, limit=limit)
    await session.commit()

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert result["failed"] == limit
    assert result["synced"] == 0
    failed_rows = [row for row in outbox_rows if row.status == SyncStatus.failed]
    pending_rows = [row for row in outbox_rows if row.status == SyncStatus.pending]
    assert len(failed_rows) == limit
    assert len(pending_rows) == 2 - limit
    for row in failed_rows:
        assert row.retries == 1
        assert row.last_attempt_at is not None
        _assert_sanitized_sync_error(row.last_error, http_status)
    assert all(row.retries == 0 and row.last_attempt_at is None for row in pending_rows)
    status = await sheets.sheets_status(session)
    assert status["counts"][SyncStatus.failed.value] == limit
    assert status["counts"].get(SyncStatus.pending.value, 0) == 2 - limit
    _assert_sanitized_sync_error(status["last_error"], http_status)
    state = await session.scalar(select(SyncState))
    assert state is not None
    assert state.remote_row_key == prior_row_key
    assert state.last_success_at == prior_success
    assert gateway.client.is_closed
    assert {
        model: await _canonical_snapshot(session, model)
        for model in (Opportunity, Assessment, Review)
    } == before


@pytest.mark.integration
async def test_sheets_header_write_failure_closes_gateway_and_marks_outbox_failed(
    session: AsyncSession, monkeypatch
) -> None:
    outbox_rows = await _enqueue_opportunities(session, monkeypatch)
    settings = _settings()

    async def fail_header(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"values": []}, request=request)
        assert request.method == "PUT"
        return httpx.Response(
            503,
            text="private header-write response details",
            request=request,
        )

    gateway, requests, _ = _mock_gateway(monkeypatch, settings, fail_header)
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)
    result = await sheets.process_sheets_outbox(session)
    await session.commit()

    assert [request.method for request in requests] == ["GET", "PUT"]
    assert result["failed"] == 1
    outbox = outbox_rows[0]
    assert outbox.status == SyncStatus.failed
    assert outbox.retries == 1
    assert outbox.last_attempt_at is not None
    _assert_sanitized_sync_error(outbox.last_error, 503)
    status = await sheets.sheets_status(session)
    assert status["counts"][SyncStatus.failed.value] == 1
    _assert_sanitized_sync_error(status["last_error"], 503)
    assert gateway.client.is_closed


@pytest.mark.integration
async def test_sheets_recovery_writes_header_once_and_reenqueued_upsert_updates_row(
    session: AsyncSession, monkeypatch
) -> None:
    outbox_rows = await _enqueue_opportunities(session, monkeypatch)
    settings = _settings()
    remote_rows: list[list[str]] = []
    fail_first_read = True
    header_writes = 0
    appends = 0
    updates = 0

    async def transport(request: httpx.Request) -> httpx.Response:
        nonlocal fail_first_read, header_writes, appends, updates
        if request.method == "GET":
            if fail_first_read:
                fail_first_read = False
                return httpx.Response(503, request=request)
            return httpx.Response(200, json={"values": remote_rows}, request=request)
        payload = json.loads(request.read())
        request_range = request.url.path.rsplit("/", 1)[-1]
        if request.method == "PUT" and request_range.endswith("A1:Q1"):
            header_writes += 1
            remote_rows[:] = payload["values"]
            return httpx.Response(200, json={}, request=request)
        if request.method == "POST":
            appends += 1
            remote_rows.extend(payload["values"])
            return httpx.Response(
                200,
                json={"updates": {"updatedRange": "Opportunities!A2:Q2"}},
                request=request,
            )
        assert request.method == "PUT"
        updates += 1
        remote_rows[1] = payload["values"][0]
        return httpx.Response(200, json={}, request=request)

    gateway, _, gateways = _mock_gateway(monkeypatch, settings, transport)
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)

    failed = await sheets.process_sheets_outbox(session)
    await session.commit()
    outbox = outbox_rows[0]
    assert failed["failed"] == 1
    assert outbox.retries == 1
    _assert_sanitized_sync_error(outbox.last_error, 503)

    recovered = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert recovered["synced"] == 1
    assert outbox.status == SyncStatus.synced
    assert outbox.last_error is None
    assert header_writes == 1
    assert appends == 1
    assert remote_rows[0] == sheets.SHEET_HEADERS
    assert len([row for row in remote_rows[1:] if row[0] == str(outbox.entity_id)]) == 1
    assert gateway.client.is_closed
    assert all(client.client.is_closed for client in gateways)
    state = await session.scalar(select(SyncState))
    assert state is not None
    assert state.last_error is None
    assert state.last_success_at is not None

    requeued_id = await sheets.enqueue_sheet_upsert(session, outbox.entity_id)
    assert requeued_id is not None
    await session.commit()
    requeued = await sheets.process_sheets_outbox(session)
    await session.commit()
    assert requeued["synced"] == 1
    assert appends == 1
    assert updates == 1
    assert len([row for row in remote_rows[1:] if row[0] == str(outbox.entity_id)]) == 1
    assert await sheets.process_sheets_outbox(session) == {
        "enabled": True,
        "configured": True,
        "synced": 0,
        "failed": 0,
        "skipped": 0,
    }


@pytest.mark.integration
async def test_sheets_retry_and_selection_limits_are_respected(
    session: AsyncSession, monkeypatch
) -> None:
    outbox_rows = await _enqueue_opportunities(session, monkeypatch, count=3)
    exhausted_rows = outbox_rows[:2]
    for outbox in exhausted_rows:
        outbox.status = SyncStatus.failed
        outbox.retries = sheets.MAX_SYNC_ATTEMPTS
    await session.commit()
    settings = _settings()
    remote_rows: list[list[str]] = []
    request_count = 0

    async def transport(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request.method == "GET":
            return httpx.Response(200, json={"values": remote_rows}, request=request)
        payload = json.loads(request.read())
        if request.method == "PUT":
            remote_rows[:] = payload["values"]
            return httpx.Response(200, json={}, request=request)
        remote_rows.extend(payload["values"])
        return httpx.Response(
            200,
            json={"updates": {"updatedRange": "Opportunities!A2:Q2"}},
            request=request,
        )

    gateway, _, _ = _mock_gateway(monkeypatch, settings, transport)
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)

    limited = await sheets.process_sheets_outbox(session, limit=1)
    await session.commit()
    assert limited["synced"] == 1
    assert limited["failed"] == 0
    assert sum(row.status == SyncStatus.synced for row in outbox_rows) == 1
    assert all(
        row.status == SyncStatus.failed and row.retries == sheets.MAX_SYNC_ATTEMPTS
        for row in exhausted_rows
    )
    no_retry = await sheets.process_sheets_outbox(session, limit=1)
    assert no_retry["synced"] == no_retry["failed"] == 0
    assert request_count == 3
    assert gateway.client.is_closed


@pytest.mark.integration
@pytest.mark.parametrize(("enabled", "configured"), [(False, True), (True, False)])
async def test_sheets_disabled_or_unconfigured_does_not_call_gateway_or_consume_retries(
    session: AsyncSession, monkeypatch, enabled: bool, configured: bool
) -> None:
    outbox_rows = await _enqueue_opportunities(session, monkeypatch)
    outbox = outbox_rows[0]
    settings = _settings(enabled=enabled, configured=configured)
    monkeypatch.setattr(sheets, "get_settings", lambda: settings)

    async def unexpected_gateway(cls, passed_settings):
        raise AssertionError("disabled or unconfigured Sheets must not create a gateway")

    monkeypatch.setattr(
        sheets.SheetsGateway, "create", classmethod(unexpected_gateway)
    )
    result = await sheets.process_sheets_outbox(session)

    assert result["enabled"] is enabled
    if not configured:
        assert result["configured"] is False
    assert result["failed"] == result["synced"] == 0
    assert outbox.status == SyncStatus.pending
    assert outbox.retries == 0
    assert outbox.last_attempt_at is None


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
