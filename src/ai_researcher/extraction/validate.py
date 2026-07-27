"""Validate LLM extraction output before any database write."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ai_researcher.extraction.schema import (
    ClaimRecord,
    DatasetRecord,
    MethodRecord,
    MetricRecord,
    ResultRecord,
)
from ai_researcher.logging import get_logger

logger = get_logger(__name__)

RECORD_MODELS = {
    "claim": ClaimRecord,
    "method": MethodRecord,
    "result": ResultRecord,
    "dataset": DatasetRecord,
    "metric": MetricRecord,
}


class MissingAnchorError(ValueError):
    """Raised when a record lacks a usable tree_node_id for the current paper."""


@dataclass(frozen=True)
class RejectedRecord:
    record: Mapping[str, Any] | Any
    error: Exception


@dataclass
class ValidationOutcome:
    accepted: list[Any] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    paper_failed: bool = False
    failure_reason: str | None = None


def _coerce_records(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parsed = json.loads(raw)
        return _coerce_records(parsed)
    if isinstance(raw, Mapping):
        if "records" in raw:
            records = raw["records"]
            if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
                msg = "records must be a list"
                raise TypeError(msg)
            return list(records)
        # Single record object.
        return [dict(raw)]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return list(raw)
    msg = f"unsupported extraction payload type: {type(raw)!r}"
    raise TypeError(msg)


def _record_type(record: Mapping[str, Any]) -> str:
    explicit = record.get("record_type") or record.get("type")
    if isinstance(explicit, str) and explicit in RECORD_MODELS:
        return explicit
    for key, name in (
        ("claim_text", "claim"),
        ("method_text", "method"),
        ("result_text", "result"),
        ("dataset_name", "dataset"),
        ("metric_name", "metric"),
    ):
        if key in record:
            return name
    msg = "unable to determine extraction record type"
    raise ValueError(msg)


def _is_anchor_failure(exc: Exception, record: Mapping[str, Any]) -> bool:
    if isinstance(exc, MissingAnchorError):
        return True
    node_id = record.get("tree_node_id", None)
    if node_id is None or node_id == "" or node_id == 0:
        return True
    if isinstance(exc, ValidationError):
        for err in exc.errors():
            loc = err.get("loc") or ()
            if loc and loc[0] == "tree_node_id":
                return True
    text = str(exc).lower()
    return "tree_node_id" in text


def validate_batch(
    raw: Any,
    allowed_node_ids: Collection[int],
) -> ValidationOutcome:
    """Validate a batch of extraction records against schema and allowed node IDs.

    Records missing ``tree_node_id`` or citing a node outside ``allowed_node_ids``
    are rejected with :class:`MissingAnchorError` and logged — never accepted.
    """

    outcome = ValidationOutcome()
    allowed = {int(n) for n in allowed_node_ids}

    try:
        records = _coerce_records(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        outcome.paper_failed = True
        outcome.failure_reason = f"malformed extraction payload: {exc}"
        logger.warning("extraction batch rejected as malformed: %s", exc)
        return outcome

    for record in records:
        if not isinstance(record, Mapping):
            err = TypeError(f"record must be a mapping, got {type(record)!r}")
            logger.warning("rejecting non-mapping extraction record: %r", record)
            outcome.rejected.append(RejectedRecord(record=record, error=err))
            continue

        payload = dict(record)
        node_id = payload.get("tree_node_id", None)
        if node_id is None or node_id == "" or node_id == 0:
            err = MissingAnchorError(
                "tree_node_id is required; unanchored records are never persisted"
            )
            logger.warning(
                "rejecting unanchored extraction record (missing tree_node_id): %r",
                payload,
            )
            outcome.rejected.append(RejectedRecord(record=payload, error=err))
            continue

        try:
            node_int = int(node_id)
        except (TypeError, ValueError):
            err = MissingAnchorError(f"tree_node_id {node_id!r} is not a valid node id")
            logger.warning(
                "rejecting extraction record with invalid tree_node_id: %r",
                payload,
            )
            outcome.rejected.append(RejectedRecord(record=payload, error=err))
            continue

        if node_int not in allowed:
            err = MissingAnchorError(
                f"tree_node_id {node_int} is outside the paper being extracted"
            )
            logger.warning(
                "rejecting cross-paper or unknown tree_node_id %s: %r",
                node_int,
                payload,
            )
            outcome.rejected.append(RejectedRecord(record=payload, error=err))
            continue

        try:
            kind = _record_type(payload)
            model_cls = RECORD_MODELS[kind]
            model_payload = {
                key: value for key, value in payload.items() if key not in {"record_type", "type"}
            }
            validated = model_cls.model_validate(model_payload)
        except Exception as exc:
            if _is_anchor_failure(exc, payload):
                err: Exception = MissingAnchorError(str(exc))
            else:
                err = exc
            logger.warning(
                "rejecting malformed extraction record %r: %s",
                payload,
                err,
            )
            outcome.rejected.append(RejectedRecord(record=payload, error=err))
            continue

        outcome.accepted.append(validated)

    return outcome


def validate_llm_output(
    fetch: Callable[[], Any],
    allowed_node_ids: Collection[int],
) -> ValidationOutcome:
    """Validate LLM extraction output, retrying malformed payloads once.

    ``fetch`` is called up to twice. After a second malformed payload the outcome
    is marked ``paper_failed`` and returned — no exception is raised.
    """

    last_reason: str | None = None
    for attempt in range(2):
        try:
            raw = fetch()
        except Exception as exc:  # noqa: BLE001 — paper-level failure, never raise
            last_reason = f"fetch failed: {exc}"
            logger.warning(
                "extraction fetch failed on attempt %s: %s",
                attempt + 1,
                exc,
            )
            continue

        try:
            # Probe JSON parseability for string payloads before schema validation.
            if isinstance(raw, str):
                json.loads(raw)
        except json.JSONDecodeError as exc:
            last_reason = f"unparseable JSON: {exc}"
            logger.warning(
                "malformed LLM extraction JSON on attempt %s: %s",
                attempt + 1,
                exc,
            )
            continue

        outcome = validate_batch(raw, allowed_node_ids)
        if outcome.paper_failed:
            last_reason = outcome.failure_reason
            logger.warning(
                "malformed LLM extraction payload on attempt %s: %s",
                attempt + 1,
                last_reason,
            )
            continue
        return outcome

    return ValidationOutcome(
        paper_failed=True,
        failure_reason=last_reason or "malformed LLM extraction output after retry",
    )


__all__ = [
    "MissingAnchorError",
    "RejectedRecord",
    "ValidationOutcome",
    "validate_batch",
    "validate_llm_output",
]
