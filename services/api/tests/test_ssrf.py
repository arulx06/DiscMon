from __future__ import annotations

import httpx
import pytest

from app.collectors.http import FetchError, FetchPolicy, SafeFetcher, validate_target


def policy(**overrides: object) -> FetchPolicy:
    values: dict[str, object] = {"timeout_seconds": 2, "max_retries": 0}
    values.update(overrides)
    return FetchPolicy(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "https://10.1.2.3/",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/",
        "https://[fd00::1]/",
        "https://[64:ff9b::7f00:1]/",
        "https://[64:ff9b::a9fe:a9fe]/",
    ],
)
async def test_private_and_metadata_targets_are_blocked(url: str) -> None:
    with pytest.raises(FetchError) as caught:
        await validate_target(url, policy())
    assert caught.value.category == "blocked_ssrf"


async def test_nat64_public_address_is_allowed() -> None:
    await validate_target("https://[64:ff9b::36f0:a23c]/", policy())


async def test_default_max_bytes_uses_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_response_bytes", 123_456)
    async with SafeFetcher(FetchPolicy()) as fetcher:
        assert fetcher.policy.max_bytes == 123_456


async def test_redirect_to_loopback_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://127.0.0.1/secret"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    async with SafeFetcher(policy(), client=client) as fetcher:
        result = await fetcher.get("https://54.240.162.60/start")
    assert result.status_code == 0
    assert result.error_class == "blocked_ssrf"


async def test_redirect_to_metadata_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    async with SafeFetcher(policy(), client=client) as fetcher:
        result = await fetcher.get("https://54.240.162.60/start")
    assert result.status_code == 0
    assert result.error_class == "blocked_ssrf"
