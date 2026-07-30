"""Offline tests for the config-driven RSS / Atom discourse adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_researcher.config import get_settings
from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.rss_blogs import RssBlogsSource

from .conftest import FIXTURES, MappingRequester

_GOOGLE_RESEARCH = "https://blog.research.google/feeds/posts/default?alt=rss"
_GOOGLE_QUANTUM = "https://blog.research.google/feeds/posts/default/-/QuantumAI"
_EXTRA_FEED = "https://example.com/feeds/extra.xml"
_BAD_FEED = "https://example.com/feeds/broken.xml"
_MISSING_FEED = "https://example.com/feeds/missing.xml"


def _rss_requester() -> MappingRequester:
    return MappingRequester(
        {
            "feeds/posts/default?alt=rss": "google-research.rss.xml",
            "feeds/posts/default/-/QuantumAI": "google-research.rss.xml",
            "feeds/extra.xml": "extra-blog.rss.xml",
            "feeds/broken.xml": "malformed.rss.xml",
        }
    )


def test_rss_implements_discourse_source_and_is_registered() -> None:
    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("rss_blogs")
    assert isinstance(source, DiscourseSource)
    assert source.name == "rss_blogs"


def test_default_feeds_include_google_research_and_quantum_ai() -> None:
    settings = get_settings()
    assert _GOOGLE_RESEARCH in settings.discourse_rss_feeds
    assert _GOOGLE_QUANTUM in settings.discourse_rss_feeds

    example = Path(__file__).resolve().parents[2] / ".env.example"
    text = example.read_text()
    assert "DISCOURSE_RSS_FEEDS=" in text
    assert "blog.research.google/feeds/posts/default?alt=rss" in text
    assert "blog.research.google/feeds/posts/default/-/QuantumAI" in text


def test_adding_feed_url_via_config_only_makes_it_pollable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DISCOURSE_RSS_FEEDS",
        f"{_GOOGLE_RESEARCH},{_EXTRA_FEED}",
    )
    requester = _rss_requester()
    source = RssBlogsSource(requester=requester)
    since = datetime(2024, 5, 1, tzinfo=UTC)

    items = list(source.poll(since))

    assert any(item.external_id.endswith("post-111") for item in items)
    extra = next(item for item in items if "extra-1" in item.external_id)
    assert extra.title == "Config-only feed post"
    assert extra.source == "rss_blogs"
    assert any("feeds/extra.xml" in url for url, _ in requester.calls)


def test_poll_parses_atom_and_filters_by_since() -> None:
    requester = _rss_requester()
    source = RssBlogsSource(
        feed_urls=(_GOOGLE_RESEARCH,),
        requester=requester,
    )
    since = datetime(2024, 5, 1, tzinfo=UTC)

    items = list(source.poll(since))

    assert len(items) == 1
    item = items[0]
    assert item.title == "Scaling quantum error correction"
    assert item.url == "https://blog.research.google/2024/06/scaling-qec.html"
    assert item.author == "Research Team"
    assert item.posted_at == datetime(2024, 6, 15, 10, 0, tzinfo=UTC)


def test_malformed_or_unreachable_feed_is_logged_and_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    requester = _rss_requester()
    source = RssBlogsSource(
        feed_urls=(_BAD_FEED, _MISSING_FEED, _EXTRA_FEED),
        requester=requester,
    )
    since = datetime(2024, 5, 1, tzinfo=UTC)

    with caplog.at_level(logging.WARNING):
        items = list(source.poll(since))

    assert len(items) == 1
    assert items[0].title == "Config-only feed post"
    assert any(
        "broken" in record.message.lower()
        or "malformed" in record.message.lower()
        or "skip" in record.message.lower()
        for record in caplog.records
    )
    assert any(
        "missing" in record.message.lower()
        or "unreachable" in record.message.lower()
        or "skip" in record.message.lower()
        for record in caplog.records
    )
    assert (FIXTURES / "malformed.rss.xml").exists()


def test_user_agent_identifies_tool_and_configured_contact() -> None:
    requester = _rss_requester()
    source = RssBlogsSource(feed_urls=(_GOOGLE_RESEARCH,), requester=requester)

    list(source.poll(datetime(2024, 5, 1, tzinfo=UTC)))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_link_targets_is_stubbed_empty_until_shared_resolver() -> None:
    source = RssBlogsSource(feed_urls=(_GOOGLE_RESEARCH,), requester=_rss_requester())
    assert (
        source.link_targets(
            DiscourseItem(
                source="rss_blogs",
                external_id="post-111",
                url="https://arxiv.org/abs/2401.01234",
                body="https://arxiv.org/abs/2401.01234",
            )
        )
        == []
    )
