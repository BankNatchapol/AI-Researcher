"""Offline tests for the Hugging Face Papers / alphaXiv discourse adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.huggingface import HuggingFacePapersSource
from ai_researcher.sources.base import PaperRef

from .conftest import MappingRequester


def _hf_requester() -> MappingRequester:
    return MappingRequester({"daily_papers": "hf-papers.json"})


def test_huggingface_implements_discourse_source_and_is_registered() -> None:
    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("huggingface")
    assert isinstance(source, DiscourseSource)
    assert source.name == "huggingface"


def test_poll_parses_daily_papers_with_attention_and_filters_by_since() -> None:
    requester = _hf_requester()
    source = HuggingFacePapersSource(requester=requester)
    since = datetime(2024, 5, 1, tzinfo=UTC)

    items = list(source.poll(since))

    assert len(items) == 1
    item = items[0]
    assert item.source == "huggingface"
    assert item.external_id == "2406.01234"
    assert item.title == "Attention Is Still All You Need"
    assert item.url == "https://huggingface.co/papers/2406.01234"
    assert item.score == 42
    assert item.num_comments == 3
    assert item.posted_at == datetime(2024, 6, 20, 8, 0, tzinfo=UTC)
    assert "daily_papers" in requester.calls[0][0]


def test_user_agent_identifies_tool_and_configured_contact() -> None:
    requester = _hf_requester()
    source = HuggingFacePapersSource(requester=requester)

    list(source.poll(datetime(2024, 5, 1, tzinfo=UTC)))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_link_targets_uses_shared_resolver() -> None:
    source = HuggingFacePapersSource(requester=_hf_requester())
    assert source.link_targets(
        DiscourseItem(
            source="huggingface",
            external_id="2406.01234",
            url="https://huggingface.co/papers/2406.01234",
            body="2406.01234",
        )
    ) == [PaperRef(source="arxiv", external_id="2406.01234")]
