"""Offline tests for the Reddit discourse adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.reddit import RedditSource

from .conftest import MappingRequester


def _reddit_requester() -> MappingRequester:
    return MappingRequester(
        {
            "api/v1/access_token": "reddit_token.json",
            "r/QuantumComputing/new": "reddit_quantumcomputing_new.json",
            "r/MachineLearning/new": "reddit_machinelearning_new.json",
        }
    )


def test_reddit_implements_discourse_source_and_is_registered() -> None:
    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("reddit")
    assert isinstance(source, DiscourseSource)
    assert source.name == "reddit"


def test_poll_uses_oauth_and_default_subreddits_and_filters_by_since() -> None:
    requester = _reddit_requester()
    source = RedditSource(requester=requester, post_requester=requester.post)
    since = datetime(2024, 5, 1, tzinfo=UTC)

    items = list(source.poll(since))

    assert {item.external_id for item in items} == {"abc123", "ml456"}
    assert all(item.source == "reddit" for item in items)
    quantum = next(item for item in items if item.external_id == "abc123")
    assert quantum.title == "Surface code breakthrough on superconducting qubits"
    assert quantum.score == 42
    assert quantum.num_comments == 7
    assert "QuantumComputing" in quantum.url

    assert requester.post_calls, "expected OAuth token POST"
    token_url, token_headers, token_body = requester.post_calls[0]
    assert "access_token" in token_url
    assert "Basic " in token_headers["Authorization"]
    assert b"grant_type=client_credentials" in token_body

    listing_urls = [url for url, _ in requester.calls]
    assert any("r/QuantumComputing/new" in url for url in listing_urls)
    assert any("r/MachineLearning/new" in url for url in listing_urls)
    for _, headers in requester.calls:
        assert headers["Authorization"] == "Bearer test-reddit-token"


def test_missing_credentials_skips_with_log_and_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    requester = _reddit_requester()
    source = RedditSource(requester=requester, post_requester=requester.post)

    with caplog.at_level(logging.INFO):
        items = list(source.poll(datetime(2024, 5, 1, tzinfo=UTC)))

    assert items == []
    assert requester.calls == []
    assert requester.post_calls == []
    assert any(
        "reddit" in record.message.lower() and "skip" in record.message.lower()
        for record in caplog.records
    )


def test_user_agent_identifies_tool_and_configured_contact() -> None:
    requester = _reddit_requester()
    source = RedditSource(requester=requester, post_requester=requester.post)

    list(source.poll(datetime(2024, 5, 1, tzinfo=UTC)))

    assert requester.post_calls or requester.calls
    headers = requester.post_calls[0][1] if requester.post_calls else requester.calls[0][1]
    user_agent = headers["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_link_targets_is_stubbed_empty_until_shared_resolver() -> None:
    source = RedditSource(requester=_reddit_requester())
    assert (
        source.link_targets(
            DiscourseItem(
                source="reddit",
                external_id="abc123",
                url="https://arxiv.org/abs/2401.01234",
                body="https://arxiv.org/abs/2401.01234",
            )
        )
        == []
    )
