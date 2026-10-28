from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.enums import AlertStatus
from app.services import alerts, ingestion
from app.services.assessment import get_or_create_profile
from tests.factories import FakeAdapter, make_candidate, make_source


@pytest.mark.integration
async def test_smtp_alert_delivery_uses_configured_channel(
    session: AsyncSession, monkeypatch
) -> None:
    settings = SimpleNamespace(
        smtp_enabled=True,
        telegram_enabled=False,
        app_base_url="https://discmon.example",
    )
    monkeypatch.setattr(alerts, "get_settings", lambda: settings)
    delivered: list[tuple[str, str]] = []

    def fake_send(subject: str, message: str) -> None:
        delivered.append((subject, message))

    monkeypatch.setattr(alerts, "_send_smtp", fake_send)
    profile = await get_or_create_profile(session)
    profile.alert_channels = ["smtp"]
    profile.quiet_hours_start = 0
    profile.quiet_hours_end = 0
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 1

    result = await alerts.deliver_pending_alerts(session)
    await session.commit()
    assert result["sent"] == 1
    assert len(delivered) == 1
    subject, message = delivered[0]
    assert "Senior Backend Engineer" in subject
    assert "https://discmon.example/opportunities/" in message
    alert = await session.scalar(select(Alert))
    assert alert is not None
    assert alert.status == AlertStatus.sent
    assert alert.provider_message_id is not None


@pytest.mark.integration
async def test_smtp_missing_configuration_leaves_alert_pending(
    session: AsyncSession, monkeypatch
) -> None:
    settings = SimpleNamespace(
        smtp_enabled=False,
        telegram_enabled=False,
        app_base_url="https://discmon.example",
    )
    monkeypatch.setattr(alerts, "get_settings", lambda: settings)
    profile = await get_or_create_profile(session)
    profile.alert_channels = ["email"]
    profile.quiet_hours_start = 0
    profile.quiet_hours_end = 0
    source = await make_source(session)
    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(ingestion, "get_adapter", lambda kind: adapter)
    await session.commit()
    outcome = await ingestion.ingest_source(session, source.id)
    await session.commit()
    assert outcome.created == 1

    result = await alerts.deliver_pending_alerts(session)
    await session.commit()
    assert result["failed"] == 1
    alert = await session.scalar(select(Alert))
    assert alert is not None
    assert alert.status == AlertStatus.pending
    assert alert.last_error_redacted is not None
    assert "SMTP" in alert.last_error_redacted
