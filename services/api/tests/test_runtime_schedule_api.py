from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api import deps, runtime_schedule
from app.config import Settings
from app.db.models.runtime_schedule import RuntimeSchedule
from app.db.session import async_session_factory, get_db
from app.main import app

TOKEN = "runtime-sync-test-token-" + "x" * 32


@pytest_asyncio.fixture
async def client(monkeypatch):
    async def override_get_db():
        async with async_session_factory() as session:
            yield session

    monkeypatch.setattr(
        runtime_schedule,
        "get_settings",
        lambda: Settings(app_env="test", runtime_sync_token=TOKEN),
    )
    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


async def _seed_schedule() -> None:
    async with async_session_factory() as session:
        session.add(
            RuntimeSchedule(
                id=1,
                revision=1,
                start_time=time(9),
                shutdown_time=time(21),
                timezone="Asia/Kolkata",
            )
        )
        await session.commit()


@pytest.mark.integration
async def test_owner_schedule_update_and_host_application(client: httpx.AsyncClient) -> None:
    await _seed_schedule()
    initial = await client.get("/v1/runtime-schedule")
    assert initial.status_code == 200
    assert initial.json()["status"] == "pending"
    assert initial.json()["duration_minutes"] == 720

    saved = await client.put(
        "/v1/runtime-schedule",
        json={"revision": 1, "start_time": "10:00", "shutdown_time": "21:00"},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.json()["status"] == "pending"
    assert saved.json()["applied_revision"] is None

    headers = {"Authorization": f"Bearer {TOKEN}"}
    host_schedule = await client.get("/runtime-sync/schedule", headers=headers)
    assert host_schedule.json() == {
        "revision": 2,
        "start_time": "10:00",
        "shutdown_time": "21:00",
        "timezone": "Asia/Kolkata",
    }
    acknowledged = await client.post(
        "/runtime-sync/ack",
        headers=headers,
        json={
            "revision": 2,
            "start_time": "10:00",
            "shutdown_time": "21:00",
            "timezone": "Asia/Kolkata",
        },
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json() == {"revision": 2, "acknowledged": True}
    current = await client.get("/v1/runtime-schedule")
    assert current.json()["status"] == "applied"
    assert current.json()["applied_start_time"] == "10:00"
    assert current.json()["last_sync_at"] is not None


@pytest.mark.integration
async def test_validation_revision_conflicts_and_error_status(client: httpx.AsyncClient) -> None:
    await _seed_schedule()
    invalid = await client.put(
        "/v1/runtime-schedule",
        json={"revision": 1, "start_time": "9:00", "shutdown_time": "21:00"},
    )
    assert invalid.status_code == 422
    incompatible = await client.put(
        "/v1/runtime-schedule",
        json={"revision": 1, "start_time": "08:00", "shutdown_time": "20:00"},
    )
    assert incompatible.status_code == 422
    assert "20:30 backup timer" in incompatible.json()["message"]

    saved = await client.put(
        "/v1/runtime-schedule",
        json={"revision": 1, "start_time": "08:00", "shutdown_time": "21:00"},
    )
    assert saved.status_code == 200
    stale_revision = await client.put(
        "/v1/runtime-schedule",
        json={"revision": 1, "start_time": "09:00", "shutdown_time": "21:00"},
    )
    assert stale_revision.status_code == 409

    host_headers = {"Authorization": f"Bearer {TOKEN}"}
    recorded = await client.post(
        "/runtime-sync/error",
        headers=host_headers,
        json={"revision": 2, "error": "controller_apply_failed"},
    )
    assert recorded.status_code == 200
    assert (await client.get("/v1/runtime-schedule")).json()["status"] == "error"
    ack = await client.post(
        "/runtime-sync/ack",
        headers=host_headers,
        json={
            "revision": 2,
            "start_time": "08:00",
            "shutdown_time": "21:00",
            "timezone": "Asia/Kolkata",
        },
    )
    assert ack.status_code == 200
    assert (await client.get("/v1/runtime-schedule")).json()["status"] == "applied"


@pytest.mark.integration
async def test_host_auth_is_separate_and_ack_rejects_changed_schedule(
    client: httpx.AsyncClient, monkeypatch
) -> None:
    await _seed_schedule()
    assert (await client.get("/runtime-sync/schedule")).status_code == 401
    wrong_token = await client.get(
        "/runtime-sync/schedule", headers={"Authorization": "Bearer " + "z" * 40}
    )
    assert wrong_token.status_code == 401

    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: Settings(
            app_env="test", owner_auth_mode="token", owner_api_token="owner-only-token"
        ),
    )
    owner_with_host_token = await client.get(
        "/v1/runtime-schedule", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert owner_with_host_token.status_code == 401


@pytest.mark.integration
async def test_concurrent_updates_use_optimistic_revision_lock(client: httpx.AsyncClient) -> None:
    await _seed_schedule()

    async def save(start: str) -> httpx.Response:
        return await client.put(
            "/v1/runtime-schedule",
            json={"revision": 1, "start_time": start, "shutdown_time": "21:00"},
        )

    first, second = await asyncio.gather(save("08:00"), save("10:00"))
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with async_session_factory() as session:
        schedule = await session.scalar(select(RuntimeSchedule).where(RuntimeSchedule.id == 1))
    assert schedule is not None and schedule.revision == 2


@pytest.mark.integration
async def test_host_acknowledgement_becomes_stale_after_three_minutes(
    client: httpx.AsyncClient,
) -> None:
    await _seed_schedule()
    async with async_session_factory() as session:
        schedule = await session.get(RuntimeSchedule, 1)
        assert schedule is not None
        schedule.applied_revision = 1
        schedule.applied_start_time = time(9)
        schedule.applied_shutdown_time = time(21)
        schedule.last_sync_at = datetime.now(UTC) - timedelta(minutes=3, seconds=1)
        await session.commit()
    result = await client.get("/v1/runtime-schedule")
    assert result.json()["status"] == "stale"
