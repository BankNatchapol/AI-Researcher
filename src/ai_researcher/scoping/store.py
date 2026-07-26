"""Persistence for reproducible topic-scope definitions."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import Connection, insert, select
from sqlalchemy.exc import IntegrityError

from ai_researcher.db import connect
from ai_researcher.db.models import scope as scope_table
from ai_researcher.scoping import ScopeDefinition

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


class DuplicateScopeError(ValueError):
    """Raised when a scope name is already persisted."""


def save_scope(
    definition: ScopeDefinition,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> None:
    """Persist one new scope row."""

    open_connection = connect if connection_factory is None else connection_factory
    try:
        with open_connection() as connection:
            connection.execute(
                insert(scope_table).values(
                    name=definition.name,
                    description=definition.description,
                    include_terms=list(definition.include_terms),
                    exclude_terms=list(definition.exclude_terms),
                    categories=list(definition.categories),
                    date_from=definition.date_from,
                    date_to=definition.date_to,
                    per_source_limit=definition.per_source_limit,
                )
            )
    except IntegrityError as error:
        raise DuplicateScopeError(f"Scope already exists: {definition.name}") from error


def load_scope(
    name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> ScopeDefinition | None:
    """Load a scope by its unique name."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        row = (
            connection.execute(select(scope_table).where(scope_table.c.name == name))
            .mappings()
            .one_or_none()
        )
    return None if row is None else _from_row(row)


def list_scopes(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[ScopeDefinition]:
    """Load every scope in stable name order."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        rows = connection.execute(select(scope_table).order_by(scope_table.c.name)).mappings().all()
    return [_from_row(row) for row in rows]


def _from_row(row: Any) -> ScopeDefinition:
    return ScopeDefinition(
        name=row["name"],
        description=row["description"],
        include_terms=tuple(row["include_terms"]),
        exclude_terms=tuple(row["exclude_terms"]),
        categories=tuple(row["categories"]),
        date_from=row["date_from"],
        date_to=row["date_to"],
        per_source_limit=row["per_source_limit"],
    )


__all__ = [
    "DuplicateScopeError",
    "list_scopes",
    "load_scope",
    "save_scope",
]
