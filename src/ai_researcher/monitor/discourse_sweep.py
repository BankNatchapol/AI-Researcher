"""Discourse sweep over enabled community-attention sources."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ai_researcher.config import get_settings
from ai_researcher.db import connect
from ai_researcher.db.models import discourse_item, discourse_mention, discourse_source, sweep_run
from ai_researcher.discourse.base import DiscourseItem, DiscourseSource
from ai_researcher.discourse.resolve import resolve_against_corpus
from ai_researcher.logging import get_logger
from ai_researcher.monitor.sweep import (
    STATE_COMPLETED,
    STATE_COMPLETED_WITH_ERRORS,
    STATE_FAILED,
    STATE_RUNNING,
    SweepResult,
)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CredentialsReadyFn = Callable[[str], bool]

logger = get_logger(__name__)

SWEEP_KIND_DISCOURSE = "discourse"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _default_credentials_ready(source_name: str) -> bool:
    """Return False only when a credential-gated source lacks its secrets."""

    if source_name != "reddit":
        return True
    settings = get_settings()
    return bool(settings.reddit_client_id and settings.reddit_client_secret)


def _registered_sources() -> tuple[DiscourseSource, ...]:
    import ai_researcher.discourse  # noqa: F401 — register built-in adapters
    from ai_researcher.discourse.registry import registered

    return registered()


def run_discourse_sweep(
    *,
    connection_factory: ConnectionFactory | None = None,
    sources: Sequence[DiscourseSource] | None = None,
    credentials_ready_fn: CredentialsReadyFn | None = None,
) -> SweepResult:
    """Poll every enabled discourse source since its last run and store items."""

    open_connection = connect if connection_factory is None else connection_factory
    credentials_ready = (
        _default_credentials_ready if credentials_ready_fn is None else credentials_ready_fn
    )
    adapters: Sequence[DiscourseSource] = (
        list(sources) if sources is not None else _registered_sources()
    )

    started_at = datetime.now(UTC)
    with open_connection() as connection:
        sweep_run_id = int(
            connection.execute(
                insert(sweep_run)
                .values(
                    kind=SWEEP_KIND_DISCOURSE,
                    started_at=started_at,
                    state=STATE_RUNNING,
                    items_found=0,
                    error=None,
                )
                .returning(sweep_run.c.id)
            ).scalar_one()
        )

    items_found = 0
    errors: list[str] = []
    skipped: list[str] = []
    attempted = 0

    for adapter in adapters:
        with open_connection() as connection:
            source_row = _ensure_source_row(connection, adapter.name)
            if not source_row["enabled"]:
                logger.info("Discourse source %s is disabled; skipping", adapter.name)
                continue

        if not credentials_ready(adapter.name):
            message = f"{adapter.name}: skipped (credentials not configured)"
            skipped.append(message)
            logger.info(
                "Discourse source %s skipped: credentials not configured",
                adapter.name,
            )
            continue

        attempted += 1
        since = source_row["last_polled_at"] or EPOCH
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        try:
            polled = list(adapter.poll(since))
            stored = _persist_items(
                open_connection,
                source_id=int(source_row["id"]),
                items=polled,
            )
            items_found += stored
            polled_at = datetime.now(UTC)
            with open_connection() as connection:
                connection.execute(
                    update(discourse_source)
                    .where(discourse_source.c.id == int(source_row["id"]))
                    .values(last_polled_at=polled_at)
                )
        except Exception as exc:  # noqa: BLE001 — one source must not abort the sweep
            message = f"{adapter.name}: {exc}"
            errors.append(message)
            logger.exception("Discourse sweep failed for source %s", adapter.name)

    if attempted == 0 and not errors:
        state = STATE_COMPLETED
    elif errors and items_found == 0 and len(errors) == attempted:
        state = STATE_FAILED
    elif errors:
        state = STATE_COMPLETED_WITH_ERRORS
    else:
        state = STATE_COMPLETED

    # Skips are recorded for observability but do not count as failures.
    error_parts = list(errors)
    if skipped and errors:
        error_parts.extend(skipped)
    error_text = "; ".join(error_parts) if error_parts else None

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
        kind=SWEEP_KIND_DISCOURSE,
        state=state,
        items_found=items_found,
        error=error_text,
    )


def _ensure_source_row(connection: Connection, name: str) -> dict:
    row = (
        connection.execute(
            select(
                discourse_source.c.id,
                discourse_source.c.enabled,
                discourse_source.c.last_polled_at,
            ).where(discourse_source.c.name == name)
        )
        .mappings()
        .first()
    )
    if row is not None:
        return dict(row)

    created = (
        connection.execute(
            insert(discourse_source)
            .values(name=name, kind=name, enabled=True, last_polled_at=None)
            .returning(
                discourse_source.c.id,
                discourse_source.c.enabled,
                discourse_source.c.last_polled_at,
            )
        )
        .mappings()
        .one()
    )
    return dict(created)


def _persist_items(
    connection_factory: ConnectionFactory,
    *,
    source_id: int,
    items: Iterable[DiscourseItem],
) -> int:
    """Store new discourse items and corpus-matched mentions; skip duplicates."""

    stored = 0
    for item in items:
        with connection_factory() as connection:
            inserted = connection.execute(
                pg_insert(discourse_item)
                .values(
                    source_id=source_id,
                    external_id=item.external_id,
                    url=item.url,
                    title=item.title,
                    author=item.author,
                    posted_at=item.posted_at,
                    score=item.score,
                    num_comments=item.num_comments,
                )
                .on_conflict_do_nothing(constraint="uq_discourse_item_source_external")
                .returning(discourse_item.c.id)
            ).scalar_one_or_none()
            if inserted is None:
                continue

            mentions = resolve_against_corpus(item, connection=connection)
            for mention in mentions:
                connection.execute(
                    insert(discourse_mention).values(
                        discourse_item_id=int(inserted),
                        paper_id=mention.paper_id,
                        resolved_by=mention.resolved_by,
                    )
                )
            stored += 1
    return stored


__all__ = [
    "EPOCH",
    "STATE_COMPLETED",
    "STATE_COMPLETED_WITH_ERRORS",
    "STATE_FAILED",
    "SWEEP_KIND_DISCOURSE",
    "SweepResult",
    "run_discourse_sweep",
]
