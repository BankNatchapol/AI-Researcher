"""Per-paper extraction orchestration with resumability and prompt versioning."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, delete, func, insert, select

from ai_researcher.config import get_settings
from ai_researcher.db import connect
from ai_researcher.db.models import (
    claim,
    dataset,
    method,
    metric,
    paper,
    paper_scope,
    result,
    section,
    tree_node,
)
from ai_researcher.db.models import scope as scope_table
from ai_researcher.extraction import prompts
from ai_researcher.extraction.schema import (
    ClaimRecord,
    DatasetRecord,
    MethodRecord,
    MetricRecord,
    ResultRecord,
)
from ai_researcher.extraction.validate import validate_llm_output
from ai_researcher.llm import gateway
from ai_researcher.logging import get_logger

ELIGIBLE_PARSE_STATUSES = ("parsed", "abstract_only")
logger = get_logger(__name__)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CompleteFn = Callable[..., str | dict]

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": ["claim", "method", "result", "dataset", "metric"],
                    },
                    "tree_node_id": {"type": "integer"},
                    "claim_text": {"type": "string"},
                    "normalized_text": {"type": "string"},
                    "claim_type": {"type": "string"},
                    "subject": {"type": ["string", "null"]},
                    "predicate": {"type": ["string", "null"]},
                    "object_value": {},
                    "unit": {"type": ["string", "null"]},
                    "method_text": {"type": "string"},
                    "result_text": {"type": "string"},
                    "dataset_name": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "metric_name": {"type": "string"},
                },
                "required": ["record_type", "tree_node_id"],
                "additionalProperties": True,
            },
        }
    },
    "required": ["records"],
    "additionalProperties": False,
}


class UnknownScopeError(LookupError):
    """Raised when extraction is requested for an unknown scope."""


class ExtractionError(RuntimeError):
    """Raised when one paper cannot be extracted."""


@dataclass(frozen=True, slots=True)
class TreeNodeInput:
    """One tree node presented to the extractor."""

    id: int
    node_path: str
    title: str | None
    summary: str
    page_start: int | None
    page_end: int | None
    depth: int
    body_text: str


@dataclass(frozen=True, slots=True)
class PaperExtractionInput:
    """A paper and its tree nodes for one batched extraction call."""

    id: int
    title: str
    abstract: str | None
    parse_status: str
    nodes: tuple[TreeNodeInput, ...]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Per-paper extraction counts by record type."""

    paper_id: int
    claims: int = 0
    methods: int = 0
    results: int = 0
    datasets: int = 0
    metrics: int = 0
    failed: bool = False
    failure_reason: str | None = None
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class ExtractScopeResult:
    """Counts reported by one resumable scope extraction run."""

    extracted: int
    skipped: int
    failed: int
    papers: tuple[ExtractionResult, ...] = ()


@dataclass
class _AcceptedBatch:
    claims: list[ClaimRecord] = field(default_factory=list)
    methods: list[MethodRecord] = field(default_factory=list)
    results: list[ResultRecord] = field(default_factory=list)
    datasets: list[DatasetRecord] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)


def current_extraction_model() -> str:
    """Return the configured backend identity used for extraction."""

    settings = get_settings()
    return settings.llm_backend_overrides.get(
        "EXTRACTION",
        settings.llm_backend_default,
    ).lower()


def _section_groups(nodes: tuple[TreeNodeInput, ...]) -> list[dict[str, Any]]:
    """Group nodes by top-level section path for the prompt payload."""

    groups: dict[str, list[TreeNodeInput]] = {}
    order: list[str] = []
    for node in nodes:
        root = node.node_path.split("/", 1)[0] if node.node_path else ""
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(node)
    return [
        {
            "section_path": root,
            "nodes": [
                {
                    "tree_node_id": node.id,
                    "node_path": node.node_path,
                    "title": node.title,
                    "summary": node.summary,
                    "page_start": node.page_start,
                    "page_end": node.page_end,
                    "depth": node.depth,
                    "body_text": node.body_text,
                }
                for node in groups[root]
            ],
        }
        for root in order
    ]


def _stamp_provenance(
    raw: Any,
    *,
    extraction_model: str,
    prompt_version: str,
) -> Any:
    """Inject extraction_model and prompt_version onto every record mapping."""

    if isinstance(raw, str):
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        stamped = _stamp_provenance(
            parsed,
            extraction_model=extraction_model,
            prompt_version=prompt_version,
        )
        return json.dumps(stamped, ensure_ascii=False)
    if isinstance(raw, dict):
        if "records" in raw and isinstance(raw["records"], list):
            return {
                **raw,
                "records": [
                    _stamp_one(
                        item,
                        extraction_model=extraction_model,
                        prompt_version=prompt_version,
                    )
                    for item in raw["records"]
                ],
            }
        return _stamp_one(raw, extraction_model=extraction_model, prompt_version=prompt_version)
    if isinstance(raw, list):
        return [
            _stamp_one(item, extraction_model=extraction_model, prompt_version=prompt_version)
            for item in raw
        ]
    return raw


def _stamp_one(
    item: Any,
    *,
    extraction_model: str,
    prompt_version: str,
) -> Any:
    if not isinstance(item, dict):
        return item
    stamped = dict(item)
    stamped["extraction_model"] = extraction_model
    stamped["prompt_version"] = prompt_version
    return stamped


def _partition_accepted(accepted: list[Any]) -> _AcceptedBatch:
    batch = _AcceptedBatch()
    for record in accepted:
        if isinstance(record, ClaimRecord):
            batch.claims.append(record)
        elif isinstance(record, MethodRecord):
            batch.methods.append(record)
        elif isinstance(record, ResultRecord):
            batch.results.append(record)
        elif isinstance(record, DatasetRecord):
            batch.datasets.append(record)
        elif isinstance(record, MetricRecord):
            batch.metrics.append(record)
    return batch


def extract_paper(
    paper_input: PaperExtractionInput,
    *,
    complete_fn: CompleteFn | None = None,
    extraction_model: str | None = None,
    prompt_version: str | None = None,
    persist: bool = True,
    connection: Connection | None = None,
) -> ExtractionResult:
    """Extract structured records from one paper using a single batched model call.

    Nodes are grouped by top-level section path in the prompt payload, but the
    gateway is invoked once per paper so call volume scales with paper count.
    """

    if not paper_input.nodes:
        raise ExtractionError(f"Paper {paper_input.id} has no tree nodes to extract")

    call_model = gateway.complete if complete_fn is None else complete_fn
    model_name = current_extraction_model() if extraction_model is None else extraction_model
    version = prompts.PROMPT_VERSION if prompt_version is None else prompt_version
    allowed_ids = {node.id for node in paper_input.nodes}

    payload = {
        "paper": {
            "id": paper_input.id,
            "title": paper_input.title,
            "abstract": paper_input.abstract,
            "parse_status": paper_input.parse_status,
        },
        "instructions": prompts.EXTRACTION_INSTRUCTIONS,
        "prompt_version": version,
        "section_groups": _section_groups(paper_input.nodes),
    }

    def fetch() -> Any:
        response = call_model(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            job="extraction",
            schema=EXTRACTION_SCHEMA,
        )
        return _stamp_provenance(
            response,
            extraction_model=model_name,
            prompt_version=version,
        )

    outcome = validate_llm_output(fetch, allowed_ids)
    if outcome.paper_failed:
        reason = outcome.failure_reason or "extraction failed"
        logger.warning("Extraction failed for paper %s: %s", paper_input.id, reason)
        return ExtractionResult(
            paper_id=paper_input.id,
            failed=True,
            failure_reason=reason,
        )

    batch = _partition_accepted(outcome.accepted)
    if persist:
        if connection is None:
            raise ExtractionError("persist=True requires an open database connection")
        _persist_extractions(connection, paper_id=paper_input.id, batch=batch)

    return ExtractionResult(
        paper_id=paper_input.id,
        claims=len(batch.claims),
        methods=len(batch.methods),
        results=len(batch.results),
        datasets=len(batch.datasets),
        metrics=len(batch.metrics),
    )


def extract_scope(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> ExtractScopeResult:
    """Extract stale papers in ``scope_name`` and continue past paper failures."""

    open_connection = connect if connection_factory is None else connection_factory
    model_name = current_extraction_model()
    version = prompts.PROMPT_VERSION

    with open_connection() as connection:
        scope_id = connection.execute(
            select(scope_table.c.id).where(scope_table.c.name == scope_name)
        ).scalar_one_or_none()
        if scope_id is None:
            raise UnknownScopeError(f"Unknown scope: {scope_name}")
        paper_rows = (
            connection.execute(
                select(
                    paper.c.id,
                    paper.c.title,
                    paper.c.abstract,
                    paper.c.parse_status,
                )
                .join(paper_scope, paper_scope.c.paper_id == paper.c.id)
                .where(
                    paper_scope.c.scope_id == scope_id,
                    paper.c.parse_status.in_(ELIGIBLE_PARSE_STATUSES),
                )
                .order_by(paper.c.id)
            )
            .mappings()
            .all()
        )

    extracted = 0
    skipped = 0
    failed = 0
    paper_results: list[ExtractionResult] = []

    for paper_row in paper_rows:
        paper_id = int(paper_row["id"])
        with open_connection() as connection:
            if _paper_extraction_is_current(connection, paper_id=paper_id, prompt_version=version):
                skipped += 1
                paper_results.append(ExtractionResult(paper_id=paper_id, skipped=True))
                continue
            paper_input = _load_paper_input(connection, paper_row)
            if not paper_input.nodes:
                skipped += 1
                paper_results.append(ExtractionResult(paper_id=paper_id, skipped=True))
                continue

        try:
            with open_connection() as connection:
                result = extract_paper(
                    paper_input,
                    extraction_model=model_name,
                    prompt_version=version,
                    persist=True,
                    connection=connection,
                )
        except Exception as exc:  # noqa: BLE001 — paper-level failure, never abort
            failed += 1
            logger.exception("Extraction failed for paper %s", paper_id)
            paper_results.append(
                ExtractionResult(
                    paper_id=paper_id,
                    failed=True,
                    failure_reason=str(exc),
                )
            )
            continue

        if result.failed:
            failed += 1
            paper_results.append(result)
            continue

        extracted += 1
        paper_results.append(result)

    return ExtractScopeResult(
        extracted=extracted,
        skipped=skipped,
        failed=failed,
        papers=tuple(paper_results),
    )


def _paper_extraction_is_current(
    connection: Connection,
    *,
    paper_id: int,
    prompt_version: str,
) -> bool:
    """A paper is current when it has any extraction row at ``prompt_version``."""

    for table in (claim, method, result, dataset, metric):
        count = connection.execute(
            select(func.count())
            .select_from(table)
            .where(
                table.c.paper_id == paper_id,
                table.c.prompt_version == prompt_version,
            )
        ).scalar_one()
        if int(count) > 0:
            return True
    return False


def _load_paper_input(connection: Connection, paper_row: Any) -> PaperExtractionInput:
    paper_id = int(paper_row["id"])
    rows = (
        connection.execute(
            select(
                tree_node.c.id,
                tree_node.c.node_path,
                tree_node.c.title,
                tree_node.c.summary,
                tree_node.c.page_start,
                tree_node.c.page_end,
                tree_node.c.depth,
                section.c.body_text,
            )
            .join(section, section.c.id == tree_node.c.section_id)
            .where(tree_node.c.paper_id == paper_id)
            .order_by(tree_node.c.depth, tree_node.c.id)
        )
        .mappings()
        .all()
    )
    return PaperExtractionInput(
        id=paper_id,
        title=str(paper_row["title"]),
        abstract=paper_row["abstract"],
        parse_status=str(paper_row["parse_status"]),
        nodes=tuple(
            TreeNodeInput(
                id=int(row["id"]),
                node_path=str(row["node_path"]),
                title=row["title"],
                summary=str(row["summary"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
                depth=int(row["depth"]),
                body_text=str(row["body_text"] or ""),
            )
            for row in rows
        ),
    )


def _persist_extractions(
    connection: Connection,
    *,
    paper_id: int,
    batch: _AcceptedBatch,
) -> None:
    """Replace prior extractions for ``paper_id`` with the newly accepted batch."""

    connection.execute(delete(claim).where(claim.c.paper_id == paper_id))
    connection.execute(delete(method).where(method.c.paper_id == paper_id))
    connection.execute(delete(result).where(result.c.paper_id == paper_id))
    connection.execute(delete(dataset).where(dataset.c.paper_id == paper_id))
    connection.execute(delete(metric).where(metric.c.paper_id == paper_id))

    if batch.claims:
        connection.execute(
            insert(claim),
            [
                {
                    "paper_id": paper_id,
                    "tree_node_id": record.tree_node_id,
                    "claim_text": record.claim_text,
                    "normalized_text": record.normalized_text,
                    "claim_type": record.claim_type,
                    "subject": record.subject,
                    "predicate": record.predicate,
                    "object_value": record.object_value,
                    "unit": record.unit,
                    "extraction_model": record.extraction_model,
                    "prompt_version": record.prompt_version,
                }
                for record in batch.claims
            ],
        )
    if batch.methods:
        connection.execute(
            insert(method),
            [
                {
                    "paper_id": paper_id,
                    "tree_node_id": record.tree_node_id,
                    "method_text": record.method_text,
                    "extraction_model": record.extraction_model,
                    "prompt_version": record.prompt_version,
                }
                for record in batch.methods
            ],
        )
    if batch.results:
        connection.execute(
            insert(result),
            [
                {
                    "paper_id": paper_id,
                    "tree_node_id": record.tree_node_id,
                    "result_text": record.result_text,
                    "extraction_model": record.extraction_model,
                    "prompt_version": record.prompt_version,
                }
                for record in batch.results
            ],
        )
    if batch.datasets:
        connection.execute(
            insert(dataset),
            [
                {
                    "paper_id": paper_id,
                    "tree_node_id": record.tree_node_id,
                    "dataset_name": record.dataset_name,
                    "description": record.description,
                    "extraction_model": record.extraction_model,
                    "prompt_version": record.prompt_version,
                }
                for record in batch.datasets
            ],
        )
    if batch.metrics:
        connection.execute(
            insert(metric),
            [
                {
                    "paper_id": paper_id,
                    "tree_node_id": record.tree_node_id,
                    "metric_name": record.metric_name,
                    "object_value": record.object_value,
                    "unit": record.unit,
                    "extraction_model": record.extraction_model,
                    "prompt_version": record.prompt_version,
                }
                for record in batch.metrics
            ],
        )


__all__ = [
    "EXTRACTION_SCHEMA",
    "ExtractionError",
    "ExtractionResult",
    "ExtractScopeResult",
    "PaperExtractionInput",
    "TreeNodeInput",
    "UnknownScopeError",
    "current_extraction_model",
    "extract_paper",
    "extract_scope",
]
