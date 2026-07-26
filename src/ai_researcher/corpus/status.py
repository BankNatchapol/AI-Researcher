"""Aggregate corpus status per scope via SQL."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from sqlalchemy import Connection, case, func, select

from ai_researcher.db import connect
from ai_researcher.db.models import paper, paper_scope, section
from ai_researcher.db.models import scope as scope_table

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


@dataclass(frozen=True, slots=True)
class FailedPaper:
    """One paper in a scope whose ``parse_status`` is ``failed``."""

    paper_id: int
    title: str
    error: str


@dataclass(frozen=True, slots=True)
class ScopeStatus:
    """Per-scope corpus counts, optionally including failed-paper details."""

    scope_name: str
    paper_count: int
    parsed_count: int
    abstract_only_count: int
    failed_count: int
    section_count: int
    failed_papers: tuple[FailedPaper, ...] = ()


def scope_status(
    scope_name: str | None = None,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[ScopeStatus]:
    """Return corpus counts for every scope, or one named scope.

    Counts are aggregated in SQL. When ``scope_name`` is set, failed papers for
    that scope are listed with their recorded ``parse_error``.
    """

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        statuses = _aggregate_counts(connection, scope_name)
        if scope_name is not None and statuses:
            failed = _failed_papers(connection, scope_name)
            return [
                ScopeStatus(
                    scope_name=item.scope_name,
                    paper_count=item.paper_count,
                    parsed_count=item.parsed_count,
                    abstract_only_count=item.abstract_only_count,
                    failed_count=item.failed_count,
                    section_count=item.section_count,
                    failed_papers=failed,
                )
                for item in statuses
            ]
        return statuses


def _aggregate_counts(
    connection: Connection,
    scope_name: str | None,
) -> list[ScopeStatus]:
    paper_query = (
        select(
            scope_table.c.name,
            func.count(paper.c.id).label("paper_count"),
            func.coalesce(
                func.sum(case((paper.c.parse_status == "parsed", 1), else_=0)),
                0,
            ).label("parsed_count"),
            func.coalesce(
                func.sum(case((paper.c.parse_status == "abstract_only", 1), else_=0)),
                0,
            ).label("abstract_only_count"),
            func.coalesce(
                func.sum(case((paper.c.parse_status == "failed", 1), else_=0)),
                0,
            ).label("failed_count"),
        )
        .select_from(scope_table)
        .outerjoin(paper_scope, paper_scope.c.scope_id == scope_table.c.id)
        .outerjoin(paper, paper.c.id == paper_scope.c.paper_id)
        .group_by(scope_table.c.name)
        .order_by(scope_table.c.name)
    )
    if scope_name is not None:
        paper_query = paper_query.where(scope_table.c.name == scope_name)

    section_query = (
        select(
            scope_table.c.name,
            func.count(section.c.id).label("section_count"),
        )
        .select_from(scope_table)
        .outerjoin(paper_scope, paper_scope.c.scope_id == scope_table.c.id)
        .outerjoin(paper, paper.c.id == paper_scope.c.paper_id)
        .outerjoin(section, section.c.paper_id == paper.c.id)
        .group_by(scope_table.c.name)
        .order_by(scope_table.c.name)
    )
    if scope_name is not None:
        section_query = section_query.where(scope_table.c.name == scope_name)

    paper_rows = connection.execute(paper_query).mappings().all()
    section_rows = {
        str(row["name"]): int(row["section_count"])
        for row in connection.execute(section_query).mappings().all()
    }

    return [
        ScopeStatus(
            scope_name=str(row["name"]),
            paper_count=int(row["paper_count"]),
            parsed_count=int(row["parsed_count"]),
            abstract_only_count=int(row["abstract_only_count"]),
            failed_count=int(row["failed_count"]),
            section_count=section_rows.get(str(row["name"]), 0),
        )
        for row in paper_rows
    ]


def _failed_papers(connection: Connection, scope_name: str) -> tuple[FailedPaper, ...]:
    query = (
        select(paper.c.id, paper.c.title, paper.c.parse_error)
        .select_from(paper)
        .join(paper_scope, paper_scope.c.paper_id == paper.c.id)
        .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
        .where(scope_table.c.name == scope_name)
        .where(paper.c.parse_status == "failed")
        .order_by(paper.c.id)
    )
    rows = connection.execute(query).mappings().all()
    return tuple(
        FailedPaper(
            paper_id=int(row["id"]),
            title=str(row["title"]),
            error=str(row["parse_error"] or ""),
        )
        for row in rows
    )


__all__ = ["FailedPaper", "ScopeStatus", "scope_status"]
