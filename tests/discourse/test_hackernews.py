"""Offline tests for the Hacker News discourse adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.hackernews import HackerNewsSource
from ai_researcher.sources.base import PaperRef

from .conftest import MappingRequester


def _hn_requester() -> MappingRequester:
    return MappingRequester(
        {
            "newstories.json": "hn_newstories.json",
            "/item/40100001.json": "hn_item_40100001.json",
            "/item/40100002.json": "hn_item_40100002.json",
            "/item/40100003.json": "hn_item_40100003.json",
        }
    )


def test_hackernews_implements_discourse_source_and_is_registered() -> None:
    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("hackernews")
    assert isinstance(source, DiscourseSource)
    assert source.name == "hackernews"


def test_poll_uses_firebase_api_and_filters_by_since_and_story_type() -> None:
    requester = _hn_requester()
    source = HackerNewsSource(requester=requester)
    since = datetime(2024, 5, 1, tzinfo=UTC)

    items = list(source.poll(since))

    assert len(items) == 1
    item = items[0]
    assert item.external_id == "40100001"
    assert item.source == "hackernews"
    assert item.title == "Quantum error correction on a surface code"
    assert item.url == "https://news.ycombinator.com/item?id=40100001"
    assert item.author == "pg"
    assert item.score == 88
    assert item.num_comments == 14
    assert "arxiv.org/abs/2402.05555" in (item.body or "")

    urls = [url for url, _ in requester.calls]
    assert any("hacker-news.firebaseio.com/v0/newstories.json" in url for url in urls)
    assert any("/item/40100001.json" in url for url in urls)


def test_user_agent_identifies_tool_and_configured_contact() -> None:
    requester = _hn_requester()
    source = HackerNewsSource(requester=requester)

    list(source.poll(datetime(2024, 5, 1, tzinfo=UTC)))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_link_targets_uses_shared_resolver() -> None:
    source = HackerNewsSource(requester=_hn_requester())
    assert source.link_targets(
        DiscourseItem(
            source="hackernews",
            external_id="40100001",
            url="https://news.ycombinator.com/item?id=40100001",
            body="https://arxiv.org/abs/2402.05555",
        )
    ) == [PaperRef(source="arxiv", external_id="2402.05555")]
