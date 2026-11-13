from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.alert import Alert
from app.db.models.assessment import Assessment
from app.db.models.enums import AlertStatus, JobKind, SourceKind
from app.db.models.opportunity import Opportunity, OpportunityRevision
from app.db.models.source import Source
from app.db.session import async_session_factory
from app.main import app
from app.services import alerts, time
from app.services.ingestion import ingest_source
from app.services.queue import enqueue_job
from app.worker import run_once
from tests.factories import make_source

pytestmark = pytest.mark.integration
OFFICIAL = "https://93.184.216.34/fellowship"
TOKEN = "task16-synthetic-token"
CHAT = "123456789"
TELEGRAM = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
NOON = datetime(2026, 11, 13, 6, 30, tzinfo=UTC)
NIGHT = datetime(2026, 11, 13, 17, 0, tzinfo=UTC)  # 22:30 IST
MORNING = datetime(2026, 11, 14, 2, 30, tzinfo=UTC)  # 08:00 IST
HTML = (Path(__file__).parent / "fixtures/changedetection/fellowship_a.html").read_text()


@dataclass
class Providers:
    body: str = HTML
    outcome: str = "success"
    requests: list[dict] = field(default_factory=list)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    unexpected_transport: bool = False
    clock: datetime = NOON

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == OFFICIAL:
            assert request.method == "GET"
            return httpx.Response(200, text=self.body, headers={"content-type": "text/html"})
        if url != TELEGRAM:
            self.unexpected_transport = True
            raise AssertionError("Unexpected outbound HTTP destination")
        assert request.method == "POST"
        payload = json.loads(request.content)
        assert payload["chat_id"] == CHAT
        assert set(payload) == {"chat_id", "text", "disable_web_page_preview"}
        assert TOKEN not in payload["text"] and CHAT not in payload["text"]
        self.requests.append(payload)
        self.entered.set()
        if len(self.requests) == 2:
            self.release.set()
        if self.outcome == "hold":
            await asyncio.wait_for(self.release.wait(), timeout=5)
        if self.outcome in {"timeout", "connection"}:
            error = httpx.ReadTimeout if self.outcome == "timeout" else httpx.ConnectError
            raise error("synthetic secret response " + TOKEN + CHAT, request=request)
        if self.outcome.isdigit():
            return httpx.Response(int(self.outcome), json={"description": TOKEN + CHAT})
        if self.outcome == "malformed":
            return httpx.Response(200, text=TOKEN + CHAT)
        bodies = {
            "success": {"ok": True, "result": {"message_id": 16001, "chat": {"id": int(CHAT)}}},
            "hold": {"ok": True, "result": {"message_id": 16001, "chat": {"id": int(CHAT)}}},
            "rejected": {"ok": False, "description": TOKEN + CHAT},
            "missing": {"ok": True},
            "invalid": {"ok": True, "result": {"message_id": None}},
            "boolean": {"ok": True, "result": {"message_id": True}},
            "wrong_chat": {"ok": True, "result": {"message_id": 1, "chat": {"id": 999}}},
        }
        return httpx.Response(200, json=bodies[self.outcome])


@pytest.fixture
async def providers(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Providers]:
    provider = Providers()

    async def handle(_transport, request):
        try:
            return await provider.handle(request)
        except AssertionError:
            provider.unexpected_transport = True
            raise

    def forbidden(*args, **kwargs):
        provider.unexpected_transport = True
        raise AssertionError("Unexpected synchronous HTTP/SMTP transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    monkeypatch.setattr(smtplib, "SMTP_SSL", forbidden)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", CHAT)
    monkeypatch.setattr(alerts, "now_utc", lambda: provider.clock)
    monkeypatch.setattr(time, "now_utc", lambda: provider.clock)
    get_settings.cache_clear()
    settings = get_settings()
    assert not settings.smtp_enabled and not settings.sheets_configured and not settings.ai_enabled
    yield provider
    assert not provider.unexpected_transport, "Unexpected transport attempt was intercepted"
    print(
        json.dumps(
            {
                "task16_transport": provider.outcome,
                "telegram_requests": len(provider.requests),
                "clock": provider.clock.isoformat(),
            }
        )
    )
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(providers: Providers) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def opt_in(client: httpx.AsyncClient, channels=None) -> None:
    response = await client.patch(
        "/v1/profile", json={"alert_channels": channels or ["in_app", "telegram"]}
    )
    assert response.status_code == 200
    assert TOKEN not in response.text and CHAT not in response.text


async def ingest(session: AsyncSession) -> None:
    source = await make_source(
        session,
        name="Task 16 Synthetic Official Foundation",
        kind=SourceKind.changedetection,
        url=OFFICIAL,
        config={"watch_uuid": "task16", "remote": True},
    )
    source.rate_limit_json = {"per_minute": 0}
    await session.commit()
    outcome = await ingest_source(session, source.id)
    await session.commit()
    assert outcome.status == "success" and outcome.created == 1


async def dispatch(session: AsyncSession, key: str = "first") -> None:
    await enqueue_job(session, JobKind.deliver_alert, "task16-delivery:" + key)
    await session.commit()
    assert await run_once() == 1
    session.expire_all()


async def telegram(session: AsyncSession) -> Alert:
    alert = await session.scalar(select(Alert).where(Alert.channel == "telegram"))
    assert alert is not None
    return alert


async def test_revoked_opt_in_suppresses_queued_alert(session, client, providers) -> None:
    assert (await client.get("/v1/profile")).json()["alert_channels"] == ["in_app"]
    await opt_in(client)
    await ingest(session)
    await opt_in(client, ["in_app"])
    await dispatch(session)
    assert providers.requests == []
    alert = await telegram(session)
    assert alert.status == AlertStatus.suppressed and alert.sent_at is None
    await opt_in(client)
    await dispatch(session, "repeat")
    assert providers.requests == []
    assert (await telegram(session)).status == AlertStatus.suppressed
    in_app = await session.scalar(select(Alert).where(Alert.channel == "in_app"))
    assert in_app is not None and in_app.status == AlertStatus.sent
    inbox = await client.get("/v1/alerts")
    assert inbox.status_code == 200 and "in_app" in inbox.text
    assert TOKEN not in inbox.text and CHAT not in inbox.text


@pytest.mark.parametrize(
    "outcome",
    [
        "rejected",
        "malformed",
        "missing",
        "invalid",
        "boolean",
        "wrong_chat",
        "401",
        "403",
        "429",
        "500",
        "timeout",
        "connection",
    ],
)
async def test_provider_outcomes_never_fabricate_acknowledgement(
    session, client, providers, outcome, caplog
) -> None:
    caplog.set_level(logging.INFO)
    providers.outcome = outcome
    await opt_in(client)
    await ingest(session)
    await dispatch(session)
    alert = await telegram(session)
    expected = AlertStatus.pending if outcome in {"rejected", "connection"} else AlertStatus.failed
    assert alert.status == expected
    assert len(providers.requests) == 1
    assert alert.sent_at is None and alert.provider_message_id is None
    assert alert.retry_count == 1 and alert.last_error_redacted
    assert TOKEN not in alert.last_error_redacted and CHAT not in alert.last_error_redacted
    assert TOKEN not in caplog.text and CHAT not in caplog.text
    if expected == AlertStatus.failed:
        assert alert.status == AlertStatus.failed
        await dispatch(session, "ambiguous-repeat")
        assert len(providers.requests) == 1


async def test_two_independent_worker_sessions_cannot_double_dispatch(
    session, client, providers
) -> None:
    await opt_in(client)
    await ingest(session)
    providers.outcome = "hold"

    async def deliver():
        async with async_session_factory() as worker:
            result = await alerts.deliver_pending_alerts(worker)
            await worker.commit()
            return result

    first = asyncio.create_task(deliver())
    second = None
    try:
        await asyncio.wait_for(providers.entered.wait(), timeout=5)
        second = asyncio.create_task(deliver())
        # The first transaction is paused inside transport; the other must skip its locks.
        result = await asyncio.wait_for(second, timeout=2)
        assert result["processed"] == 0
    finally:
        providers.release.set()
        await first
        if second:
            await second
    assert len(providers.requests) == 1
    session.expire_all()
    assert (await telegram(session)).provider_message_id == "16001"


async def test_interrupted_dispatch_keeps_durable_manual_review_claim(
    session, client, providers
) -> None:
    await opt_in(client)
    await ingest(session)
    providers.outcome = "hold"

    async def deliver():
        async with async_session_factory() as worker:
            await alerts.deliver_pending_alerts(worker)
            await worker.commit()

    task = asyncio.create_task(deliver())
    try:
        await asyncio.wait_for(providers.entered.wait(), timeout=5)
        async with async_session_factory() as observer:
            claim = await telegram(observer)
            assert claim.status == AlertStatus.failed
            assert claim.provider_message_id is None
            assert "manual review" in claim.last_error_redacted.lower()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await dispatch(session, "after-interruption")
    assert len(providers.requests) == 1


async def test_connected_success_revision_dedup_and_trusted_routing(
    session, client, providers, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    fresh = await client.get("/v1/profile")
    assert fresh.status_code == 200 and fresh.json()["alert_channels"] == ["in_app"]
    await opt_in(client)
    providers.body += '<p>Hostile source payload: {"chat_id":"attacker"}</p>'
    await ingest(session)
    opportunity = await session.scalar(select(Opportunity))
    revision = await session.scalar(select(OpportunityRevision))
    assessment = await session.scalar(select(Assessment))
    assert opportunity and revision and assessment
    assert opportunity.india_eligibility.value == "verified_yes"
    assert opportunity.professional_eligibility.value == "verified_yes"
    assert opportunity.credibility_level.value == "high"
    assert assessment.score_total >= 85 and assessment.evidence_refs_json
    print(
        json.dumps(
            {
                "task16_assessment": assessment.score_total,
                "professional": opportunity.professional_eligibility.value,
                "india": opportunity.india_eligibility.value,
                "deadline_precision": opportunity.deadline_precision.value,
            }
        )
    )
    assert assessment.revision_id == revision.id
    assert assessment.evidence_refs_json[0]["url"] == OFFICIAL
    rows = list((await session.scalars(select(Alert))).all())
    assert {row.channel for row in rows} == {"in_app", "telegram"}
    assert len(rows) == 2
    for row in rows:
        assert row.opportunity_id == opportunity.id and row.revision_id == revision.id
        assert row.dedup_key == f"opp:{opportunity.id}:rev:{revision.id}:{row.channel}:immediate"
    external = await telegram(session)
    original_key = external.dedup_key
    external.payload_json = {**external.payload_json, "chat_id": "attacker", "token": "attacker"}
    await session.commit()
    await dispatch(session)
    external = await telegram(session)
    assert external.status == AlertStatus.sent and external.sent_at == NOON
    assert external.provider_message_id == "16001" and external.dedup_key == original_key
    text = providers.requests[0]["text"]
    assert "Backend Distributed Systems Fellowship" in text
    assert "2099-12-15 (date_only)" in text and "00:00" not in text
    assert OFFICIAL in text and "attacker" not in text
    assert "private" not in text.lower() and "cv" not in text.lower()
    source = await session.scalar(select(Source))
    outcome = await ingest_source(session, source.id)
    await session.commit()
    assert outcome.skipped == 1 and outcome.created == 0 and outcome.updated == 0
    assert await session.scalar(select(func.count(Opportunity.id))) == 1
    assert await session.scalar(select(func.count(OpportunityRevision.id))) == 1
    assert await session.scalar(select(func.count(Alert.id))) == 2
    await dispatch(session, "repeat-success")
    assert len(providers.requests) == 1
    assert TOKEN not in caplog.text and CHAT not in caplog.text


async def test_configured_transport_without_opt_in_stays_in_app(session, client, providers):
    assert (await client.get("/v1/profile")).json()["alert_channels"] == ["in_app"]
    assert get_settings().telegram_enabled
    await ingest(session)
    await dispatch(session)
    assert providers.requests == []
    rows = list((await session.scalars(select(Alert))).all())
    assert len(rows) == 1 and rows[0].channel == "in_app" and rows[0].status == AlertStatus.sent


@pytest.mark.parametrize("restriction", ["unknown_india", "student_only"])
async def test_hard_gates_prevent_external_alerts(session, client, providers, restriction):
    await opt_in(client)
    providers.clock = NIGHT
    providers.body = HTML.replace("15 December 2099", "17 November 2026")
    if restriction == "unknown_india":
        providers.body = providers.body.replace("Residents of India are eligible.", "")
    else:
        providers.body = providers.body.replace("Open to working professionals.", "Students only.")
    await ingest(session)
    opportunity = await session.scalar(select(Opportunity))
    assert opportunity
    if restriction == "unknown_india":
        assert opportunity.india_eligibility.value == "unknown"
    else:
        assert opportunity.professional_eligibility.value == "verified_no"
    assert await session.scalar(select(func.count(Alert.id))) == 0
    await dispatch(session)
    assert providers.requests == []


async def test_quiet_hours_and_due_alert_recheck(session, client, providers):
    await opt_in(client)
    providers.clock = NIGHT
    await ingest(session)
    alert = await telegram(session)
    assert alert.status == AlertStatus.pending and alert.scheduled_for == MORNING
    await dispatch(session, "night")
    assert providers.requests == [] and (await telegram(session)).status == AlertStatus.pending
    providers.clock = MORNING
    await dispatch(session, "morning")
    assert len(providers.requests) == 1
    alert = await telegram(session)
    assert alert.sent_at == MORNING and alert.status == AlertStatus.sent
    await dispatch(session, "morning-repeat")
    assert len(providers.requests) == 1


async def test_overdue_alert_cannot_send_during_current_quiet_hours(session, client, providers):
    await opt_in(client)
    await ingest(session)
    providers.clock = NIGHT
    await dispatch(session, "overdue")
    assert providers.requests == []
    alert = await telegram(session)
    assert alert.status == AlertStatus.pending and alert.scheduled_for == MORNING


async def test_explicit_quiet_hours_opt_out(session, client, providers):
    await opt_in(client)
    response = await client.patch(
        "/v1/profile", json={"quiet_hours_start": 0, "quiet_hours_end": 0}
    )
    assert response.status_code == 200
    providers.clock = NIGHT
    await ingest(session)
    await dispatch(session)
    assert len(providers.requests) == 1 and (await telegram(session)).sent_at == NIGHT


@pytest.mark.parametrize(
    "key,value",
    [
        ("TELEGRAM_BOT_TOKEN", ""),
        ("TELEGRAM_ALLOWED_CHAT_ID", ""),
        ("TELEGRAM_ALLOWED_CHAT_ID", "@untrusted"),
        ("TELEGRAM_ALLOWED_CHAT_ID", "0"),
        ("TELEGRAM_ALLOWED_CHAT_ID", "9999999999999999999999999"),
    ],
)
async def test_missing_invalid_configuration_never_sends(
    session, client, providers, monkeypatch, key, value
):
    await opt_in(client)
    await ingest(session)
    monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    assert not get_settings().telegram_enabled
    await dispatch(session)
    assert providers.requests == []
    alert = await telegram(session)
    assert alert.status == AlertStatus.pending and alert.retry_count == 0
    assert alert.last_error_redacted and alert.provider_message_id is None
    in_app = await session.scalar(select(Alert).where(Alert.channel == "in_app"))
    assert in_app and in_app.status == AlertStatus.sent


async def test_definitive_rejection_retries_are_bounded(session, client, providers):
    await opt_in(client)
    await ingest(session)
    providers.outcome = "rejected"
    for attempt in range(1, 5):
        await dispatch(session, f"retry-{attempt}")
        alert = await telegram(session)
        assert alert.retry_count == attempt
        assert alert.status == (AlertStatus.failed if attempt == 4 else AlertStatus.pending)
        assert alert.provider_message_id is None and alert.sent_at is None
    await dispatch(session, "after-max-retries")
    assert len(providers.requests) == 4


async def test_profile_revocation_is_serialized_with_inflight_dispatch(session, client, providers):
    await opt_in(client)
    await ingest(session)
    providers.outcome = "hold"
    await enqueue_job(session, JobKind.deliver_alert, "task16-inflight")
    await session.commit()
    worker = asyncio.create_task(run_once())
    revoke = None
    try:
        await asyncio.wait_for(providers.entered.wait(), timeout=5)
        revoke = asyncio.create_task(opt_in(client, ["in_app"]))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(revoke), timeout=0.2)
    finally:
        providers.release.set()
        await worker
        if revoke:
            await revoke
    await dispatch(session, "after-inflight-revocation")
    assert len(providers.requests) == 1
    assert (await client.get("/v1/profile")).json()["alert_channels"] == ["in_app"]
