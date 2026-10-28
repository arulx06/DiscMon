from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import routes
from app.db.models.job import Job
from app.db.models.source import Source
from app.db.session import get_db
from app.main import app as fastapi_app
from tests.factories import FakeAdapter, make_candidate


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    async def override_get_db():
        yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    fastapi_app.dependency_overrides.clear()


async def _allow_source_url(monkeypatch) -> None:
    async def noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(routes, "validate_target", noop)


@pytest.mark.integration
async def test_source_create_preview_run_and_retire(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    await _allow_source_url(monkeypatch)

    rejected = await client.post(
        "/v1/sources",
        json={
            "name": "Unreviewed source",
            "source_kind": "ats_greenhouse",
            "root_url": "https://boards-api.greenhouse.io/v1/boards/example/jobs",
            "enabled": True,
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "http_error"
    assert rejected.json()["request_id"]

    created = await client.post(
        "/v1/sources",
        json={
            "name": "Example ATS",
            "source_kind": "ats_greenhouse",
            "root_url": "https://boards-api.greenhouse.io/v1/boards/example/jobs",
            "config_json": {
                "board_token": "example",
                "organization_name": "Example",
                "organization_domain": "example.com",
            },
            "officialness": "official",
            "enabled": True,
            "approval_status": "approved",
            "legal_review_status": "approved",
            "interval_hours": 12,
        },
    )
    assert created.status_code == 201
    source_body = created.json()
    source_id = source_body["id"]
    assert source_body["enabled"] is True
    assert source_body["next_due_at"] is not None

    listing = await client.get("/v1/sources")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == source_id

    detail = await client.get(f"/v1/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["config_json"]["board_token"] == "example"

    patched = await client.patch(
        f"/v1/sources/{source_id}", json={"name": "Renamed ATS", "interval_hours": 6}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed ATS"
    assert patched.json()["interval_hours"] == 6

    adapter = FakeAdapter([make_candidate()])
    monkeypatch.setattr(routes, "get_adapter", lambda kind: adapter)
    preview = await client.post(f"/v1/sources/{source_id}/test")
    assert preview.status_code == 200
    assert preview.json()["ok"] is True
    assert preview.json()["records_seen"] == 1
    assert preview.json()["preview"][0]["title"] == "Senior Backend Engineer"

    run = await client.post(f"/v1/sources/{source_id}/run")
    assert run.status_code == 200
    assert run.json()["source_id"] == source_id
    duplicate = await client.post(f"/v1/sources/{source_id}/run")
    assert duplicate.status_code == 409
    job = await session.scalar(select(Job))
    assert job is not None
    assert job.source_id is not None

    runs = await client.get(f"/v1/sources/{source_id}/runs")
    assert runs.status_code == 200
    assert runs.json()["items"] == []

    retired = await client.delete(f"/v1/sources/{source_id}")
    assert retired.status_code == 200
    assert retired.json()["enabled"] is False
    assert retired.json()["approval_status"] == "retired"
    stored = await session.get(Source, source_id)
    assert stored is not None
    assert stored.approval_status.value == "retired"
