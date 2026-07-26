"""Offline tests for the arXiv evidence adapter."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from ai_researcher.sources.arxiv import ArxivSource

from .conftest import FakeClock, FixtureRequester


@pytest.fixture
def scope() -> SimpleNamespace:
    return SimpleNamespace(
        include_terms=("quantum error correction",),
        exclude_terms=("biomedicine",),
        categories=("quant-ph",),
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
    )


def test_search_filters_by_category_and_date_and_parses_atom_fixture(scope) -> None:
    requester = FixtureRequester("arxiv_feed.xml")
    source = ArxivSource(requester=requester)

    refs = list(source.search(scope, limit=5))

    assert refs[0].external_id == "2401.01234v2"
    assert refs[0].doi == "10.1234/example.1"
    query = parse_qs(urlparse(requester.calls[0][0]).query)
    assert query["max_results"] == ["5"]
    assert "cat:quant-ph" in query["search_query"][0]
    assert "submittedDate:[202401010000 TO 202412312359]" in query["search_query"][0]
    assert 'ANDNOT all:"biomedicine"' in query["search_query"][0]
    assert "AND ANDNOT" not in query["search_query"][0]


def test_fetch_metadata_and_pdf_url_use_the_recorded_entry(scope) -> None:
    requester = FixtureRequester("arxiv_feed.xml")
    source = ArxivSource(requester=requester)
    ref = next(iter(source.search(scope, limit=1)))

    metadata = source.fetch_metadata(ref)

    assert metadata.title == "Fault-tolerant quantum memories"
    assert metadata.authors == ("Ada Researcher", "Ben Scientist")
    assert metadata.arxiv_id == "2401.01234v2"
    assert metadata.published_at == date(2024, 1, 12)
    assert source.pdf_url(ref) == "https://arxiv.org/pdf/2401.01234v2"


def test_user_agent_identifies_tool_and_configured_contact(scope) -> None:
    requester = FixtureRequester("arxiv_feed.xml")
    source = ArxivSource(requester=requester)

    list(source.search(scope, limit=1))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_two_consecutive_calls_observe_configured_arxiv_interval(scope) -> None:
    clock = FakeClock()
    requester = FixtureRequester("arxiv_feed.xml")
    source = ArxivSource(
        requester=requester,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    list(source.search(scope, limit=1))
    list(source.search(scope, limit=1))

    assert clock.sleeps == [3.0]
