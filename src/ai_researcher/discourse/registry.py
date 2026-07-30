"""Registry for community-attention discourse adapter instances.

Separate from ``ai_researcher.sources.registry`` so attention adapters can
never be looked up as evidence sources (or vice versa).
"""

from ai_researcher.discourse.base import DiscourseSource


class UnknownDiscourseSourceError(LookupError):
    """Raised when no discourse adapter is registered under a requested name."""


_SOURCES: dict[str, DiscourseSource] = {}


def register(source: DiscourseSource) -> None:
    """Register a discourse source by its declared name."""

    _SOURCES[source.name] = source


def get(name: str) -> DiscourseSource:
    """Return the registered discourse adapter named ``name``."""

    try:
        return _SOURCES[name]
    except KeyError as error:
        raise UnknownDiscourseSourceError(f"Unknown discourse source: {name}") from error


def registered() -> tuple[DiscourseSource, ...]:
    """Return every registered discourse adapter in registration order."""

    return tuple(_SOURCES.values())
