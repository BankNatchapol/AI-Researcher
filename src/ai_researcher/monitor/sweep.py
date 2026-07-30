"""Evidence sweep over active topic subscriptions."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, func, insert, select, update

from ai_researcher.db import connect
from ai_researcher.db.models import paper_scope, sweep_run
from ai_researcher.ingest.pipeline import CORPUS_CEILING
from ai_researcher.logging import get_logger
from ai_researcher.monitor.subscription import list_subscriptions

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
IngestFn = Callable[..., Any]
IndexFn = Callable[..., Any]
ExtractFn = Callable[..., Any]
LinkFn = Callable[..., Any]
ScoreFn = Callable[..., Any]

logger = get_logger(__name__)

SWEEP_KIND_EVIDENCE = "evidence"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_COMPLETED_WITH_ERRORS = "completed_with_errors"
STATE_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Terminal summary of one evidence sweep run."""

    sweep_run_id: int
    kind: str
    state: str
    items_found: int
    error: str | None


def _default_ingest(scope_name: str, *, connection_factory: ConnectionFactory | None = None) -> Any:
    """Call ingest via live module attributes so tests can monkeypatch stages."""

    from ai_researcher.ingest import pipeline

    return pipeline.run_ingest(
        scope_name,
        connection_factory=connection_factory,
        discover_fn=pipeline.discover_candidates,
        acquire_fn=pipeline.acquire_pdf,
        parse_fn=pipeline.parse_pdf,
    )


def run_evidence_sweep(
    *,
    connection_factory: ConnectionFactory | None = None,
    ingest_fn: IngestFn | None = None,
    index_fn: IndexFn | None = None,
    extract_fn: ExtractFn | None = None,
    link_fn: LinkFn | None = None,
    score_fn: ScoreFn | None = None,
) -> SweepResult:
    """Discover and fully process new papers for every active topic subscription."""

    open_connection = connect if connection_factory is None else connection_factory
    run_ingest_stage = _default_ingest if ingest_fn is None else ingest_fn

    if index_fn is None:
        from ai_researcher.trees.build import index_scope as default_index

        run_index = default_index
    else:
        run_index = index_fn

    if extract_fn is None:
        from ai_researcher.extraction.pipeline import extract_scope as default_extract

        run_extract = default_extract
    else:
        run_extract = extract_fn

    if link_fn is None:
        from ai_researcher.evidence.link import link_scope_evidence as default_link

        run_link = default_link
    else:
        run_link = link_fn

    if score_fn is None:
        from ai_researcher.scoring.confidence import score_scope_confidence as default_score

        run_score = default_score
    else:
        run_score = score_fn

    started_at = datetime.now(UTC)
    with open_connection() as connection:
        sweep_run_id = int(
            connection.execute(
                insert(sweep_run)
                .values(
                    kind=SWEEP_KIND_EVIDENCE,
                    started_at=started_at,
                    state=STATE_RUNNING,
                    items_found=0,
                    error=None,
                )
                .returning(sweep_run.c.id)
            ).scalar_one()
        )

    subscriptions = [
        record
        for record in list_subscriptions(connection_factory=open_connection)
        if record.active and record.kind == "topic" and record.scope_id is not None
    ]

    items_found = 0
    errors: list[str] = []

    for record in subscriptions:
        scope_name = record.target
        try:
            items_found += _sweep_scope(
                scope_name,
                scope_id=int(record.scope_id),
                connection_factory=open_connection,
                ingest_fn=run_ingest_stage,
                index_fn=run_index,
                extract_fn=run_extract,
                link_fn=run_link,
                score_fn=run_score,
            )
        except Exception as exc:  # noqa: BLE001 — one scope must not abort the sweep
            message = f"{scope_name}: {exc}"
            errors.append(message)
            logger.exception("Evidence sweep failed for scope %s", scope_name)

    if not subscriptions:
        state = STATE_COMPLETED
    elif errors and items_found == 0 and len(errors) == len(subscriptions):
        state = STATE_FAILED
    elif errors:
        state = STATE_COMPLETED_WITH_ERRORS
    else:
        state = STATE_COMPLETED

    error_text = "; ".join(errors) if errors else None
    finished_at = datetime.now(UTC)
    with open_connection() as connection:
        connection.execute(
            update(sweep_run)
            .where(sweep_run.c.id == sweep_run_id)
            .values(
                finished_at=finished_at,
                state=state,
                items_found=items_found,
                error=error_text,
            )
        )

    return SweepResult(
        sweep_run_id=sweep_run_id,
        kind=SWEEP_KIND_EVIDENCE,
        state=state,
        items_found=items_found,
        error=error_text,
    )


def _sweep_scope(
    scope_name: str,
    *,
    scope_id: int,
    connection_factory: ConnectionFactory,
    ingest_fn: IngestFn,
    index_fn: IndexFn,
    extract_fn: ExtractFn,
    link_fn: LinkFn,
    score_fn: ScoreFn,
) -> int:
    """Run ingest → index → extract → link → rescore for one subscribed scope."""

    with connection_factory() as connection:
        before_count = _paper_count(connection, scope_id)

    if before_count >= CORPUS_CEILING:
        logger.info(
            "Scope %s is already at the %s-paper ceiling; stopping adding papers",
            scope_name,
            CORPUS_CEILING,
        )
        return 0

    ingest_fn(scope_name, connection_factory=connection_factory)

    with connection_factory() as connection:
        after_count = _paper_count(connection, scope_id)

    newly_added = max(0, after_count - before_count)

    index_fn(scope_name, connection_factory=connection_factory)
    extract_fn(scope_name, connection_factory=connection_factory)
    link_fn(scope_name)
    score_fn(scope_name)
    return newly_added


def _paper_count(connection: Connection, scope_id: int) -> int:
    count = connection.execute(
        select(func.count()).select_from(paper_scope).where(paper_scope.c.scope_id == scope_id)
    ).scalar_one()
    return int(count)


__all__ = [
    "CORPUS_CEILING",
    "STATE_COMPLETED",
    "STATE_COMPLETED_WITH_ERRORS",
    "STATE_FAILED",
    "SWEEP_KIND_EVIDENCE",
    "SweepResult",
    "run_evidence_sweep",
]
