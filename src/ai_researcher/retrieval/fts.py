"""PostgreSQL full-text fallback for corpus shortlisting."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import Connection, text

from ai_researcher.db import connect
from ai_researcher.retrieval.shortlist import validate_shortlist_request

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]

SHORTLIST_SQL = text(
    """
    WITH search_query AS (
        SELECT websearch_to_tsquery('english', :question) AS value
    ),
    section_matches AS (
        SELECT
            section.paper_id,
            MAX(
                ts_rank_cd(
                    to_tsvector('english', section.body_text),
                    search_query.value
                )
            ) AS rank
        FROM section
        CROSS JOIN search_query
        WHERE to_tsvector('english', section.body_text) @@ search_query.value
        GROUP BY section.paper_id
    )
    SELECT paper.id
    FROM paper
    JOIN paper_scope ON paper_scope.paper_id = paper.id
    JOIN scope ON scope.id = paper_scope.scope_id
    CROSS JOIN search_query
    LEFT JOIN section_matches ON section_matches.paper_id = paper.id
    WHERE scope.name = :scope
      AND (
        to_tsvector(
            'english',
            coalesce(paper.title, '') || ' ' || coalesce(paper.abstract, '')
        ) @@ search_query.value
        OR section_matches.paper_id IS NOT NULL
      )
    ORDER BY
        GREATEST(
            ts_rank_cd(
                to_tsvector(
                    'english',
                    coalesce(paper.title, '') || ' ' || coalesce(paper.abstract, '')
                ),
                search_query.value
            ),
            coalesce(section_matches.rank, 0)
        ) DESC,
        paper.id
    LIMIT :limit
    """
)


class PostgresFTSShortlist:
    """Rank papers with PostgreSQL full-text search over metadata and sections."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def shortlist(self, scope: str, question: str, limit: int) -> list[int]:
        """Return full-text matches from the requested scope in rank order."""

        validate_shortlist_request(scope, question, limit)
        with self._connection_factory() as connection:
            rows = connection.execute(
                SHORTLIST_SQL,
                {"scope": scope, "question": question, "limit": limit},
            ).scalars()
            return [int(paper_id) for paper_id in rows]


__all__ = ["PostgresFTSShortlist"]
