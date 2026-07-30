"""Create, list, and deactivate topic and claim subscriptions."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, insert, select, update

from ai_researcher.db import connect
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import subscription as subscription_table

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


class UnknownScopeError(LookupError):
    """Raised when a topic subscription names a scope that does not exist."""


class UnknownClaimError(LookupError):
    """Raised when a claim subscription names a claim that does not exist."""


class UnknownSubscriptionError(LookupError):
    """Raised when unsubscribe targets a missing subscription id."""


class DuplicateSubscriptionError(ValueError):
    """Raised when an active subscription already exists for the target."""


class SubscriptionTargetError(ValueError):
    """Raised when a subscription violates the exactly-one-target rule."""


@dataclass(frozen=True, slots=True)
class Subscription:
    """One subscription row with a display target for listing."""

    id: int
    kind: str
    scope_id: int | None
    claim_id: int | None
    active: bool
    created_at: datetime
    target: str


def subscribe_topic(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> Subscription:
    """Create an active topic subscription for a saved scope."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        scope_row = (
            connection.execute(select(scope_table).where(scope_table.c.name == scope_name))
            .mappings()
            .one_or_none()
        )
        if scope_row is None:
            raise UnknownScopeError(f"Unknown scope: {scope_name}")

        scope_id = int(scope_row["id"])
        _assert_exactly_one_target(kind="topic", scope_id=scope_id, claim_id=None)
        _reject_duplicate(
            connection,
            kind="topic",
            scope_id=scope_id,
            claim_id=None,
        )
        subscription_id = int(
            connection.execute(
                insert(subscription_table)
                .values(
                    kind="topic",
                    scope_id=scope_id,
                    claim_id=None,
                    active=True,
                )
                .returning(subscription_table.c.id)
            ).scalar_one()
        )
        return _load_by_id(connection, subscription_id)


def subscribe_claim(
    claim_id: int,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> Subscription:
    """Create an active claim subscription targeting the canonical claim."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        claim_row = (
            connection.execute(select(claim_table).where(claim_table.c.id == claim_id))
            .mappings()
            .one_or_none()
        )
        if claim_row is None:
            raise UnknownClaimError(f"Unknown claim: {claim_id}")

        canonical_id = int(claim_row["canonical_claim_id"] or claim_row["id"])
        _assert_exactly_one_target(kind="claim", scope_id=None, claim_id=canonical_id)
        _reject_duplicate(
            connection,
            kind="claim",
            scope_id=None,
            claim_id=canonical_id,
        )
        subscription_id = int(
            connection.execute(
                insert(subscription_table)
                .values(
                    kind="claim",
                    scope_id=None,
                    claim_id=canonical_id,
                    active=True,
                )
                .returning(subscription_table.c.id)
            ).scalar_one()
        )
        return _load_by_id(connection, subscription_id)


def list_subscriptions(
    *,
    connection_factory: ConnectionFactory | None = None,
) -> list[Subscription]:
    """List every subscription (active and inactive) in stable id order."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        rows = (
            connection.execute(
                select(
                    subscription_table.c.id,
                    subscription_table.c.kind,
                    subscription_table.c.scope_id,
                    subscription_table.c.claim_id,
                    subscription_table.c.active,
                    subscription_table.c.created_at,
                    scope_table.c.name.label("scope_name"),
                )
                .select_from(
                    subscription_table.outerjoin(
                        scope_table,
                        subscription_table.c.scope_id == scope_table.c.id,
                    )
                )
                .order_by(subscription_table.c.id)
            )
            .mappings()
            .all()
        )
    return [_from_row(row) for row in rows]


def unsubscribe(
    subscription_id: int,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> Subscription:
    """Deactivate a subscription without deleting its row."""

    open_connection = connect if connection_factory is None else connection_factory
    with open_connection() as connection:
        existing = connection.execute(
            select(subscription_table.c.id).where(subscription_table.c.id == subscription_id)
        ).scalar_one_or_none()
        if existing is None:
            raise UnknownSubscriptionError(f"Unknown subscription: {subscription_id}")

        connection.execute(
            update(subscription_table)
            .where(subscription_table.c.id == subscription_id)
            .values(active=False)
        )
        return _load_by_id(connection, subscription_id)


def _assert_exactly_one_target(
    *,
    kind: str,
    scope_id: int | None,
    claim_id: int | None,
) -> None:
    topic_ok = kind == "topic" and scope_id is not None and claim_id is None
    claim_ok = kind == "claim" and claim_id is not None and scope_id is None
    if not (topic_ok or claim_ok):
        raise SubscriptionTargetError("Subscription requires exactly one of scope_id or claim_id")


def _reject_duplicate(
    connection: Connection,
    *,
    kind: str,
    scope_id: int | None,
    claim_id: int | None,
) -> None:
    query = select(subscription_table.c.id).where(
        subscription_table.c.kind == kind,
        subscription_table.c.active.is_(True),
    )
    if kind == "topic":
        query = query.where(subscription_table.c.scope_id == scope_id)
        label = f"scope_id={scope_id}"
    else:
        query = query.where(subscription_table.c.claim_id == claim_id)
        label = f"claim_id={claim_id}"

    existing = connection.execute(query).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSubscriptionError(f"Duplicate subscription for {label}")


def _load_by_id(connection: Connection, subscription_id: int) -> Subscription:
    row = (
        connection.execute(
            select(
                subscription_table.c.id,
                subscription_table.c.kind,
                subscription_table.c.scope_id,
                subscription_table.c.claim_id,
                subscription_table.c.active,
                subscription_table.c.created_at,
                scope_table.c.name.label("scope_name"),
            )
            .select_from(
                subscription_table.outerjoin(
                    scope_table,
                    subscription_table.c.scope_id == scope_table.c.id,
                )
            )
            .where(subscription_table.c.id == subscription_id)
        )
        .mappings()
        .one()
    )
    return _from_row(row)


def _from_row(row: Any) -> Subscription:
    kind = str(row["kind"])
    if kind == "topic":
        target = str(row["scope_name"] or row["scope_id"])
    else:
        target = str(row["claim_id"])
    return Subscription(
        id=int(row["id"]),
        kind=kind,
        scope_id=None if row["scope_id"] is None else int(row["scope_id"]),
        claim_id=None if row["claim_id"] is None else int(row["claim_id"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        target=target,
    )


__all__ = [
    "DuplicateSubscriptionError",
    "Subscription",
    "SubscriptionTargetError",
    "UnknownClaimError",
    "UnknownScopeError",
    "UnknownSubscriptionError",
    "list_subscriptions",
    "subscribe_claim",
    "subscribe_topic",
    "unsubscribe",
]
