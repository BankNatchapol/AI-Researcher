"""Vectorless corpus retrieval interfaces."""

from ai_researcher.retrieval.fts import PostgresFTSShortlist
from ai_researcher.retrieval.shortlist import (
    Shortlist,
    get_shortlist_backend,
    register_shortlist_backend,
    registered_shortlist_backends,
    shortlist,
)
from ai_researcher.trees.corpus import PageIndexShortlist

register_shortlist_backend("pageindex", PageIndexShortlist)
register_shortlist_backend("postgres_fts", PostgresFTSShortlist)

__all__ = [
    "PageIndexShortlist",
    "PostgresFTSShortlist",
    "Shortlist",
    "get_shortlist_backend",
    "registered_shortlist_backends",
    "shortlist",
]
