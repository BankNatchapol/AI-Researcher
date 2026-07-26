"""Offline DOI-resolution tests for the non-discovery Crossref helper."""

from urllib.parse import parse_qs, urlparse

from ai_researcher.sources.crossref import resolve_doi

from .conftest import FixtureRequester


def test_resolve_doi_uses_recorded_crossref_response() -> None:
    requester = FixtureRequester("crossref_works.json")

    doi = resolve_doi("Fault-tolerant quantum memories", requester=requester)

    assert doi == "10.1234/example.1"
    query = parse_qs(urlparse(requester.calls[0][0]).query)
    assert query["query.title"] == ["Fault-tolerant quantum memories"]
    assert query["rows"] == ["1"]
    user_agent = requester.calls[0][1]["User-Agent"]
    assert "AI-Researcher" in user_agent
    assert "researcher@example.com" in user_agent
