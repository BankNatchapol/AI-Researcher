"""Swappable corpus-shortlisting protocol and backend registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from ai_researcher.config import InvalidConfigurationError, get_settings


@runtime_checkable
class Shortlist(Protocol):
    """Narrow a named scope to relevant paper IDs without vector search."""

    def shortlist(self, scope: str, question: str, limit: int) -> list[int]:
        """Return at most ``limit`` relevant paper IDs from ``scope``."""


_BACKENDS: dict[str, type[Shortlist]] = {}


def register_shortlist_backend(name: str, implementation: type[Shortlist]) -> None:
    """Register one shortlist implementation under its configuration name."""

    existing = _BACKENDS.get(name)
    if existing is not None and existing is not implementation:
        raise ValueError(f"Shortlist backend {name!r} is already registered")
    _BACKENDS[name] = implementation


def registered_shortlist_backends() -> Mapping[str, type[Shortlist]]:
    """Return a snapshot of registered shortlist implementations."""

    return dict(_BACKENDS)


def get_shortlist_backend(name: str | None = None) -> Shortlist:
    """Construct the configured shortlist implementation."""

    backend_name = get_settings().shortlist_backend if name is None else name
    try:
        implementation = _BACKENDS[backend_name]
    except KeyError as error:
        available = ", ".join(sorted(_BACKENDS))
        raise InvalidConfigurationError(
            f"Unknown SHORTLIST_BACKEND {backend_name!r}; choose one of: {available}"
        ) from error
    return implementation()


def shortlist(scope: str, question: str, limit: int) -> list[int]:
    """Shortlist papers using the backend selected by ``SHORTLIST_BACKEND``."""

    return get_shortlist_backend().shortlist(scope, question, limit)


def validate_shortlist_request(scope: str, question: str, limit: int) -> None:
    """Validate arguments shared by all shortlist implementations."""

    if not scope.strip():
        raise ValueError("scope must not be empty")
    if not question.strip():
        raise ValueError("question must not be empty")
    if limit < 1:
        raise ValueError("limit must be a positive integer")


__all__ = [
    "Shortlist",
    "get_shortlist_backend",
    "register_shortlist_backend",
    "registered_shortlist_backends",
    "shortlist",
]
