"""DiscourseSource protocol and registry tests."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from ai_researcher.discourse import registry
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.sources.base import PaperRef


class _StubDiscourseSource:
    name = "stub"

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        del since
        return ()

    def link_targets(self, item: DiscourseItem) -> list[PaperRef]:
        del item
        return []


def test_register_and_get_returns_adapter() -> None:
    previous = dict(registry._SOURCES)
    try:
        registry._SOURCES.clear()
        adapter = _StubDiscourseSource()
        registry.register(adapter)

        got = registry.get("stub")

        assert got is adapter
        assert isinstance(got, DiscourseSource)
        assert got.name == "stub"
    finally:
        registry._SOURCES.clear()
        registry._SOURCES.update(previous)


def test_unknown_discourse_source_raises_named_error() -> None:
    previous = dict(registry._SOURCES)
    try:
        registry._SOURCES.clear()
        with pytest.raises(registry.UnknownDiscourseSourceError, match="nope"):
            registry.get("nope")
    finally:
        registry._SOURCES.clear()
        registry._SOURCES.update(previous)


def test_discourse_source_protocol_requires_poll_and_link_targets() -> None:
    adapter = _StubDiscourseSource()
    assert isinstance(adapter, DiscourseSource)
    items = list(adapter.poll(datetime(2024, 1, 1, tzinfo=UTC)))
    assert items == []
    assert (
        adapter.link_targets(
            DiscourseItem(
                source="stub",
                external_id="1",
                url="https://example.com/1",
            )
        )
        == []
    )
