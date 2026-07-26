"""Offline tests for the OpenAlex evidence adapter."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from ai_researcher.sources.openalex import OpenAlexSource

from .conftest import FakeClock, FixtureRequester


@pytest.fixture
def scope() -> SimpleNamespace:
    return SimpleNamespace(
        include_terms=("quantum error correction",),
        exclude_terms=(),
        categories=("quant-ph",),
        date_from=date(2023, 1, 1),
        date_to=date(2024, 6, 30),
    )


def test_search_uses_publication_date_filters_and_parses_fixture(scope) -> None:
    requester = FixtureRequester("openalex_search.json")
    source = OpenAlexSource(requester=requester)

    refs = list(source.search(scope, limit=7))

    assert refs[0].external_id == "W123456789"
    assert refs[0].doi == "10.1234/example.1"
    assert refs[0].pdf_url == "https://example.org/openalex-paper.pdf"
    assert source.pdf_url(refs[0]) == "https://example.org/openalex-paper.pdf"
    query = parse_qs(urlparse(requester.calls[0][0]).query)
    assert query["search"] == ["quantum error correction"]
    assert query["per-page"] == ["7"]
    assert "from_publication_date:2023-01-01" in query["filter"][0]
    assert "to_publication_date:2024-06-30" in query["filter"][0]


def test_fetch_metadata_reconstructs_abstract_from_recorded_fixture(scope) -> None:
    search_requester = FixtureRequester("openalex_search.json")
    source = OpenAlexSource(requester=search_requester)
    ref = next(iter(source.search(scope, limit=1)))
    source.requester = FixtureRequester("openalex_work.json")

    metadata = source.fetch_metadata(ref)

    assert metadata.title == "Logical qubits with lower overhead"
    assert metadata.abstract == "Quantum codes reduce physical errors."
    assert metadata.authors == ("Carla Theorist", "Dan Experimentalist")
    assert metadata.openalex_id == "W123456789"
    assert metadata.published_at == date(2024, 2, 20)
    assert metadata.pdf_url == "https://example.org/openalex-paper.pdf"


def test_user_agent_identifies_tool_and_configured_contact(scope) -> None:
    requester = FixtureRequester("openalex_search.json")
    source = OpenAlexSource(requester=requester)

    list(source.search(scope, limit=1))

    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent


def test_two_consecutive_calls_observe_configured_openalex_interval(scope) -> None:
    clock = FakeClock()
    requester = FixtureRequester("openalex_search.json")
    source = OpenAlexSource(
        requester=requester,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    list(source.search(scope, limit=1))
    list(source.search(scope, limit=1))

    assert clock.sleeps == pytest.approx([0.2])
