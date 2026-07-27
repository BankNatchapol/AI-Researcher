"""Vectorless corpus retrieval interfaces."""

from ai_researcher.retrieval.shortlist import (
    Shortlist,
    get_shortlist_backend,
    register_shortlist_backend,
    registered_shortlist_backends,
    shortlist,
)


def __getattr__(name: str) -> type[Shortlist]:
    """Load concrete backends only when callers request them."""

    backend_names = {
        "PageIndexShortlist": "pageindex",
        "PostgresFTSShortlist": "postgres_fts",
    }
    try:
        backend_name = backend_names[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    return registered_shortlist_backends()[backend_name]


__all__ = [
    "PageIndexShortlist",
    "PostgresFTSShortlist",
    "Shortlist",
    "get_shortlist_backend",
    "register_shortlist_backend",
    "registered_shortlist_backends",
    "shortlist",
]
