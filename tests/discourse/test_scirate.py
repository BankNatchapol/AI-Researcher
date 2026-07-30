"""Offline tests for the SciRate discourse spike adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.response import addinfourl

import pytest

from ai_researcher.config import get_settings
from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.scirate import SciRateSource
from ai_researcher.sources.base import PaperRef

from .conftest import MappingRequester

_FIXTURES = Path(__file__).parent / "fixtures"
_ARXIV_ID = "2402.05555"
_SCIRATE_URL = f"https://scirate.com/arxiv/{_ARXIV_ID}"


def _scirate_requester() -> MappingRequester:
    return MappingRequester({f"/arxiv/{_ARXIV_ID}": "scirate_arxiv_2402_05555.html"})


def test_scirate_implements_discourse_source_and_is_registered() -> None:
    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("scirate")
    assert isinstance(source, DiscourseSource)
    assert source.name == "scirate"


def test_discourse_scirate_enabled_defaults_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISCOURSE_SCIRATE_ENABLED", raising=False)

    settings = get_settings()

    assert settings.discourse_scirate_enabled is False


def test_disabled_by_default_poll_makes_no_http_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISCOURSE_SCIRATE_ENABLED", raising=False)
    requester = _scirate_requester()
    source = SciRateSource(requester=requester, arxiv_ids=(_ARXIV_ID,))

    items = list(source.poll(datetime(2024, 1, 1, tzinfo=UTC)))

    assert items == []
    assert requester.calls == []


def test_discourse_sweep_does_not_contact_scirate_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag unset ⇒ sweep path must not hit scirate.com (adapter poll is the contact point)."""

    monkeypatch.delenv("DISCOURSE_SCIRATE_ENABLED", raising=False)
    calls: list[str] = []

    def tracking_requester(url: str, headers: dict[str, str]) -> bytes:
        calls.append(url)
        raise AssertionError(f"unexpected HTTP contact: {url}")

    import ai_researcher.discourse  # noqa: F401 — registers adapters

    source = registry.get("scirate")
    assert isinstance(source, SciRateSource)
    # Rebind a tracking requester on a fresh instance matching sweep usage.
    probe = SciRateSource(requester=tracking_requester, arxiv_ids=(_ARXIV_ID,))
    list(probe.poll(datetime(1970, 1, 1, tzinfo=UTC)))

    assert calls == []
    assert not any("scirate.com" in url for url in calls)


def test_enabled_fetch_stores_only_scite_count_arxiv_id_and_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCOURSE_SCIRATE_ENABLED", "true")
    requester = _scirate_requester()
    source = SciRateSource(requester=requester, arxiv_ids=(_ARXIV_ID,))

    items = list(source.poll(datetime(2024, 1, 1, tzinfo=UTC)))

    assert len(items) == 1
    item = items[0]
    assert item.source == "scirate"
    assert item.external_id == _ARXIV_ID
    assert item.url == _SCIRATE_URL
    assert item.score == 42
    assert item.body is None
    assert item.title is None
    assert item.author is None
    assert item.num_comments is None
    assert requester.calls
    assert all("scirate.com/arxiv/" in url for url, _ in requester.calls)
    # Fixture HTML must not leak into stored fields.
    raw = (_FIXTURES / "scirate_arxiv_2402_05555.html").read_text()
    assert "This long abstract" in raw
    assert item.body is None


def test_stored_row_shape_excludes_page_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored DiscourseItem shape for a successful fetch: signal fields only."""

    monkeypatch.setenv("DISCOURSE_SCIRATE_ENABLED", "true")
    source = SciRateSource(requester=_scirate_requester(), arxiv_ids=(_ARXIV_ID,))
    item = list(source.poll(datetime(2024, 1, 1, tzinfo=UTC)))[0]

    stored = {
        "external_id": item.external_id,
        "url": item.url,
        "score": item.score,
        "body": item.body,
        "title": item.title,
        "author": item.author,
        "num_comments": item.num_comments,
    }
    assert stored == {
        "external_id": _ARXIV_ID,
        "url": _SCIRATE_URL,
        "score": 42,
        "body": None,
        "title": None,
        "author": None,
        "num_comments": None,
    }


def test_http_403_degrades_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCOURSE_SCIRATE_ENABLED", "true")

    def forbidden(url: str, headers: dict[str, str]) -> bytes:
        raise HTTPError(
            url,
            403,
            "Forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=addinfourl(BytesIO(b"challenge"), {}, url),
        )

    source = SciRateSource(requester=forbidden, arxiv_ids=(_ARXIV_ID,))
    items = list(source.poll(datetime(2024, 1, 1, tzinfo=UTC)))
    assert items == []


def test_link_targets_resolves_arxiv_from_scirate_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCOURSE_SCIRATE_ENABLED", "true")
    source = SciRateSource(requester=_scirate_requester(), arxiv_ids=(_ARXIV_ID,))
    item = DiscourseItem(
        source="scirate",
        external_id=_ARXIV_ID,
        url=_SCIRATE_URL,
        score=42,
    )
    assert source.link_targets(item) == [PaperRef(source="arxiv", external_id=_ARXIV_ID)]


def test_design_doc_records_spike_outcome() -> None:
    path = Path("docs/supersaiyan/designs/scirate-spike.md")
    assert path.is_file(), "scirate-spike.md must exist"
    text = path.read_text()
    assert "outcome" in text.lower() or "Outcome" in text
    assert "recommend" in text.lower()
    assert "403" in text or "Cloudflare" in text or "defer" in text.lower()


def test_env_example_documents_scirate_flag() -> None:
    text = Path(".env.example").read_text()
    assert "DISCOURSE_SCIRATE_ENABLED" in text
