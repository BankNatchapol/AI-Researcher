"""Offline tests for FlareSolverrClient."""

import json

import pytest

from ai_researcher.sources.flaresolverr import (
    FlareSolverrClient,
    FlareSolverrNotConfiguredError,
    FlareSolverrRequestError,
    FlareSolverrResponseError,
)

from .conftest import FakeClock, FixturePostRequester

_TARGET_URL = "https://example.com/paper/123"


def test_fetch_returns_resolved_html_from_successful_response() -> None:
    requester = FixturePostRequester("flaresolverr_success.json")
    client = FlareSolverrClient(
        flaresolverr_url="http://localhost:8191/v1",
        post_requester=requester,
    )

    html = client.fetch(_TARGET_URL)

    assert html == "<html><body><h1>Example paper</h1></body></html>"
    url, headers, body = requester.calls[0]
    assert url == "http://localhost:8191/v1"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {
        "cmd": "request.get",
        "url": _TARGET_URL,
        "maxTimeout": 60_000,
    }


def test_fetch_raises_request_error_on_flaresolverr_status_error() -> None:
    requester = FixturePostRequester("flaresolverr_error.json")
    client = FlareSolverrClient(
        flaresolverr_url="http://localhost:8191/v1",
        post_requester=requester,
    )

    with pytest.raises(FlareSolverrRequestError, match="Timeout"):
        client.fetch(_TARGET_URL)


def test_fetch_raises_not_configured_error_when_url_missing() -> None:
    client = FlareSolverrClient()

    with pytest.raises(FlareSolverrNotConfiguredError):
        client.fetch(_TARGET_URL)


def test_fetch_reads_url_from_settings_when_not_passed_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLARESOLVERR_URL", "http://localhost:8191/v1")
    requester = FixturePostRequester("flaresolverr_success.json")
    client = FlareSolverrClient(post_requester=requester)

    client.fetch(_TARGET_URL)

    assert requester.calls[0][0] == "http://localhost:8191/v1"


def test_fetch_respects_minimum_interval_between_calls() -> None:
    clock = FakeClock()
    requester = FixturePostRequester("flaresolverr_success.json")
    client = FlareSolverrClient(
        flaresolverr_url="http://localhost:8191/v1",
        post_requester=requester,
        clock=clock.monotonic,
        sleeper=clock.sleep,
        min_interval_seconds=1.0,
    )

    client.fetch(_TARGET_URL)
    client.fetch(_TARGET_URL)

    assert clock.sleeps == [1.0]


def test_fetch_raises_response_error_when_resolved_page_is_non_2xx() -> None:
    requester = FixturePostRequester("flaresolverr_success_404.json")
    client = FlareSolverrClient(
        flaresolverr_url="http://localhost:8191/v1",
        post_requester=requester,
    )

    with pytest.raises(FlareSolverrResponseError) as excinfo:
        client.fetch(_TARGET_URL)
    assert excinfo.value.status_code == 404


def test_fetch_wraps_http_error_from_flaresolverr_itself() -> None:
    def unreachable(url: str, headers: dict[str, str], body: bytes) -> bytes:
        raise ConnectionRefusedError("connection refused")

    client = FlareSolverrClient(
        flaresolverr_url="http://localhost:8191/v1",
        post_requester=unreachable,
    )

    with pytest.raises(FlareSolverrRequestError, match="Could not reach FlareSolverr"):
        client.fetch(_TARGET_URL)
