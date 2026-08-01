"""Offline tests for SourceHttp's shared retry/backoff behavior."""

from urllib.error import HTTPError

import pytest

from ai_researcher.sources._http import SourceHttp

from .conftest import FakeClock, SequencedResponses, make_http_error

_URL = "https://example.com/paper/search"


def _http(requester) -> SourceHttp:
    clock = FakeClock()
    http = SourceHttp(
        "semantic_scholar",
        requester=requester,
        post_requester=requester,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )
    return http, clock


def test_get_retries_after_429_then_succeeds() -> None:
    requester = SequencedResponses([make_http_error(_URL, 429), b"payload"])
    http, clock = _http(requester)

    result = http.get(_URL)

    assert result == b"payload"
    assert len(requester.calls) == 2
    assert clock.sleeps == [2.0]


def test_get_retries_up_to_max_attempts_then_raises() -> None:
    requester = SequencedResponses(
        [
            make_http_error(_URL, 429),
            make_http_error(_URL, 429),
            make_http_error(_URL, 429),
            make_http_error(_URL, 429),
        ]
    )
    http, clock = _http(requester)

    with pytest.raises(HTTPError) as excinfo:
        http.get(_URL)
    assert excinfo.value.code == 429

    assert len(requester.calls) == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]


def test_get_does_not_retry_non_retryable_status() -> None:
    requester = SequencedResponses([make_http_error(_URL, 404)])
    http, clock = _http(requester)

    with pytest.raises(HTTPError) as excinfo:
        http.get(_URL)
    assert excinfo.value.code == 404

    assert len(requester.calls) == 1
    assert clock.sleeps == []


def test_get_retries_on_5xx() -> None:
    requester = SequencedResponses([make_http_error(_URL, 503), b"payload"])
    http, clock = _http(requester)

    result = http.get(_URL)

    assert result == b"payload"
    assert clock.sleeps == [2.0]


def test_get_honors_retry_after_header() -> None:
    requester = SequencedResponses([make_http_error(_URL, 429, retry_after="5"), b"payload"])
    http, clock = _http(requester)

    result = http.get(_URL)

    assert result == b"payload"
    assert clock.sleeps == [5.0]


def test_post_also_retries() -> None:
    requester = SequencedResponses([make_http_error(_URL, 429), b"payload"])
    http, clock = _http(requester)

    result = http.post(_URL, body=b"{}", content_type="application/json")

    assert result == b"payload"
    assert len(requester.calls) == 2
    assert clock.sleeps == [2.0]
