"""Evidence-source protocol and registry tests."""

import pytest

from ai_researcher.sources import registry
from ai_researcher.sources.base import EvidenceSource


@pytest.mark.parametrize("name", ["arxiv", "openalex", "semantic_scholar"])
def test_builtin_source_is_registered_at_import_time(name: str) -> None:
    adapter = registry.get(name)

    assert isinstance(adapter, EvidenceSource)
    assert adapter.name == name


def test_unknown_source_raises_named_error() -> None:
    with pytest.raises(registry.UnknownSourceError, match="nope"):
        registry.get("nope")


def test_crossref_is_not_registered_as_a_discovery_source() -> None:
    with pytest.raises(registry.UnknownSourceError, match="crossref"):
        registry.get("crossref")
