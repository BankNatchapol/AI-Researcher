"""Registry for scholarly evidence-source adapter instances."""

from ai_researcher.sources.base import EvidenceSource


class UnknownSourceError(LookupError):
    """Raised when no evidence adapter is registered under a requested name."""


_SOURCES: dict[str, EvidenceSource] = {}


def register(source: EvidenceSource) -> None:
    """Register an evidence source by its declared name."""

    _SOURCES[source.name] = source


def get(name: str) -> EvidenceSource:
    """Return the registered adapter named ``name``."""

    try:
        return _SOURCES[name]
    except KeyError as error:
        raise UnknownSourceError(f"Unknown evidence source: {name}") from error


def registered() -> tuple[EvidenceSource, ...]:
    """Return every registered evidence adapter in registration order."""

    return tuple(_SOURCES.values())
