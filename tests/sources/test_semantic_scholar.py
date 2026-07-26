"""Offline tests for the Semantic Scholar evidence adapter."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from ai_researcher.sources.semantic_scholar import SemanticScholarSource

from .conftest import FakeClock, FixtureRequester


@pytest.fixture
def scope() -> SimpleNamespace:
    return SimpleNamespace(
        include_terms=("quantum error correction",),
        exclude_terms=(),
        categories=("quant-ph",),
        date_from=date(2022, 1, 1),
        date_to=date(2024, 12, 31),
    )


def test_search_uses_date_range_and_parses_recorded_fixture(scope) -> None:
    requester = FixtureRequester("semantic_scholar_search.json")
    source = SemanticScholarSource(requester=requester)

    refs = list(source.search(scope, limit=9))

    assert refs[0].external_id == "S2-PAPER-123"
    assert refs[0].doi == "10.1234/example.1"
    assert source.pdf_url(refs[0]) == "https://example.org/s2-paper.pdf"
    query = parse_qs(urlparse(requester.calls[0][0]).query)
    assert query["query"] == ["quantum error correction"]
    assert query["limit"] == ["9"]
    assert query["publicationDateOrYear"] == ["2022-01-01:2024-12-31"]


def test_fetch_metadata_parses_recorded_paper(scope) -> None:
    search_requester = FixtureRequester("semantic_scholar_search.json")
    source = SemanticScholarSource(requester=search_requester)
    ref = next(iter(source.search(scope, limit=1)))
    source.requester = FixtureRequester("semantic_scholar_paper.json")

    metadata = source.fetch_metadata(ref)

    assert metadata.title == "Decoding surface codes efficiently"
    assert metadata.abstract == "A decoder for experimentally relevant noise."
    assert metadata.authors == ("Eve Decoder", "Finn Quantum")
    assert metadata.s2_id == "S2-PAPER-123"
    assert metadata.published_at == date(2024, 3, 15)


def test_user_agent_identifies_tool_and_configured_contact(scope) -> None:
    requester = FixtureRequester("semantic_scholar_search.json")
    source = SemanticScholarSource(requester=requester)

    list(source.search(scope, limit=1))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_two_consecutive_calls_observe_configured_semantic_scholar_interval(scope) -> None:
    clock = FakeClock()
    requester = FixtureRequester("semantic_scholar_search.json")
    source = SemanticScholarSource(
        requester=requester,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    list(source.search(scope, limit=1))
    list(source.search(scope, limit=1))

    assert clock.sleeps == [1.0]
