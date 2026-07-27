"""Convert persisted paper sections into cached vectorless node trees."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, delete, func, insert, select

from ai_researcher.db import connect
from ai_researcher.db.models import paper, paper_scope, section, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.llm import gateway
from ai_researcher.logging import get_logger
from ai_researcher.trees.version import (
    TREE_SCHEMA_VERSION,
    TreeVersionState,
    current_summary_model,
    is_stale,
)

MAX_TREE_DEPTH = 4
MAX_SUMMARY_WORDS = 60
ELIGIBLE_PARSE_STATUSES = ("parsed", "abstract_only")
logger = get_logger(__name__)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CompleteFn = Callable[..., str | dict]

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "integer"},
                    "summary": {"type": "string"},
                },
                "required": ["section_id", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["summaries"],
    "additionalProperties": False,
}


class TreeBuildError(RuntimeError):
    """Raised when one paper cannot be converted into a valid tree."""


class UnknownScopeError(LookupError):
    """Raised when tree indexing is requested for an unknown scope."""


@dataclass(frozen=True, slots=True)
class SectionTreeInput:
    """A persisted section consumed by the pure tree builder."""

    id: int
    parent_id: int | None
    section_path: str
    title: str | None
    ordinal: int
    page_start: int | None
    page_end: int | None
    body_text: str


@dataclass(frozen=True, slots=True)
class PaperTreeInput:
    """A paper and all sections needed for one batched summary call."""

    id: int
    title: str
    abstract: str | None
    parse_status: str
    sections: tuple[SectionTreeInput, ...]


@dataclass(frozen=True, slots=True)
class TreeNode:
    """An unpersisted tree node anchored to exactly one source section."""

    paper_id: int
    section_id: int
    parent_section_id: int | None
    node_path: str
    title: str | None
    summary: str
    page_start: int | None
    page_end: int | None
    depth: int
    tree_schema_version: str
    summary_model: str


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Counts reported by one resumable scope indexing run."""

    built: int
    skipped: int
    failed: int


def build_tree(
    paper_input: PaperTreeInput,
    *,
    complete_fn: CompleteFn | None = None,
    summary_model: str | None = None,
) -> list[TreeNode]:
    """Build one paper tree using exactly one batched model request."""

    if not paper_input.sections:
        raise TreeBuildError(f"Paper {paper_input.id} has no sections to index")

    ordered_sections, original_depths = _order_sections(paper_input.sections)
    call_model = gateway.complete if complete_fn is None else complete_fn
    model_name = current_summary_model() if summary_model is None else summary_model
    payload = {
        "paper": {
            "id": paper_input.id,
            "title": paper_input.title,
            "abstract": paper_input.abstract,
        },
        "instructions": (
            "Return one concise factual summary per section. Each summary must contain "
            f"no more than {MAX_SUMMARY_WORDS} words."
        ),
        "sections": [
            {
                "section_id": item.id,
                "section_path": item.section_path,
                "title": item.title,
                "body_text": item.body_text,
            }
            for item in ordered_sections
        ],
    }
    response = call_model(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        job="node_summary",
        schema=SUMMARY_SCHEMA,
    )
    summaries = _validated_summaries(response, ordered_sections)

    ancestors = _ancestor_ids(ordered_sections)
    nodes: list[TreeNode] = []
    for item in ordered_sections:
        original_depth = original_depths[item.id]
        nodes.append(
            TreeNode(
                paper_id=paper_input.id,
                section_id=item.id,
                parent_section_id=_flattened_parent_id(
                    item,
                    original_depth=original_depth,
                    ancestors=ancestors,
                    original_depths=original_depths,
                ),
                node_path=item.section_path,
                title=item.title,
                summary=_truncate_summary(summaries[item.id]),
                page_start=item.page_start,
                page_end=item.page_end,
                depth=min(original_depth, MAX_TREE_DEPTH),
                tree_schema_version=TREE_SCHEMA_VERSION,
                summary_model=model_name,
            )
        )
    return nodes


def index_scope(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> IndexResult:
    """Build stale paper trees in ``scope_name`` and continue past paper failures."""

    open_connection = connect if connection_factory is None else connection_factory
    model_name = current_summary_model()

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

    built = 0
    skipped = 0
    failed = 0
    for paper_row in paper_rows:
        paper_id = int(paper_row["id"])
        with open_connection() as connection:
            if _paper_tree_is_current(
                connection,
                paper_id=paper_id,
                parse_status=str(paper_row["parse_status"]),
                summary_model=model_name,
            ):
                skipped += 1
                continue
            paper_input = _load_paper_input(connection, paper_row)

        try:
            nodes = build_tree(paper_input, summary_model=model_name)
            with open_connection() as connection:
                _persist_tree(connection, paper_id=paper_id, nodes=nodes)
        except Exception:
            failed += 1
            logger.exception("Tree build failed for paper %s", paper_id)
            continue
        built += 1

    return IndexResult(built=built, skipped=skipped, failed=failed)


def _order_sections(
    sections: tuple[SectionTreeInput, ...],
) -> tuple[list[SectionTreeInput], dict[int, int]]:
    by_id = {item.id: item for item in sections}
    if len(by_id) != len(sections):
        raise TreeBuildError("Section IDs must be unique within a paper")

    pending = sorted(sections, key=lambda item: (item.ordinal, item.id))
    ordered: list[SectionTreeInput] = []
    depths: dict[int, int] = {}
    while pending:
        progressed = False
        for item in tuple(pending):
            if item.parent_id is not None and item.parent_id not in by_id:
                raise TreeBuildError(f"Section {item.id} refers to missing parent {item.parent_id}")
            if item.parent_id is None or item.parent_id in depths:
                depths[item.id] = 0 if item.parent_id is None else depths[item.parent_id] + 1
                ordered.append(item)
                pending.remove(item)
                progressed = True
        if not progressed:
            raise TreeBuildError("Section hierarchy contains a cycle")
    return ordered, depths


def _ancestor_ids(sections: list[SectionTreeInput]) -> dict[int, tuple[int, ...]]:
    by_id = {item.id: item for item in sections}
    result: dict[int, tuple[int, ...]] = {}
    for item in sections:
        ancestors: list[int] = []
        parent_id = item.parent_id
        while parent_id is not None:
            ancestors.append(parent_id)
            parent_id = by_id[parent_id].parent_id
        result[item.id] = tuple(ancestors)
    return result


def _flattened_parent_id(
    item: SectionTreeInput,
    *,
    original_depth: int,
    ancestors: dict[int, tuple[int, ...]],
    original_depths: dict[int, int],
) -> int | None:
    if original_depth <= MAX_TREE_DEPTH:
        return item.parent_id
    target_depth = MAX_TREE_DEPTH - 1
    return next(
        ancestor_id
        for ancestor_id in ancestors[item.id]
        if original_depths[ancestor_id] == target_depth
    )


def _validated_summaries(
    response: str | dict,
    sections: list[SectionTreeInput],
) -> dict[int, str]:
    if not isinstance(response, dict) or not isinstance(response.get("summaries"), list):
        raise TreeBuildError("Node summary model returned an invalid object")

    expected_ids = {item.id for item in sections}
    summaries: dict[int, str] = {}
    for record in response["summaries"]:
        if not isinstance(record, dict):
            raise TreeBuildError("Node summary model returned an invalid summary record")
        section_id = record.get("section_id")
        summary = record.get("summary")
        if (
            not isinstance(section_id, int)
            or section_id not in expected_ids
            or section_id in summaries
            or not isinstance(summary, str)
            or not summary.strip()
        ):
            raise TreeBuildError("Node summary model returned an invalid summary record")
        summaries[section_id] = summary.strip()
    if set(summaries) != expected_ids:
        raise TreeBuildError("Node summary model did not summarize every section exactly once")
    return summaries


def _truncate_summary(summary: str) -> str:
    return " ".join(summary.split()[:MAX_SUMMARY_WORDS])


def _paper_tree_is_current(
    connection: Connection,
    *,
    paper_id: int,
    parse_status: str,
    summary_model: str,
) -> bool:
    version_rows = connection.execute(
        select(
            tree_node.c.tree_schema_version,
            tree_node.c.summary_model,
            func.count().label("node_count"),
        )
        .where(tree_node.c.paper_id == paper_id)
        .group_by(tree_node.c.tree_schema_version, tree_node.c.summary_model)
    ).all()
    if len(version_rows) != 1:
        return False

    version = TreeVersionState(
        tree_schema_version=str(version_rows[0].tree_schema_version),
        summary_model=str(version_rows[0].summary_model),
    )
    if is_stale(version, summary_model=summary_model):
        return False

    expected_count = 1
    if parse_status == "parsed":
        expected_count = int(
            connection.execute(
                select(func.count()).select_from(section).where(section.c.paper_id == paper_id)
            ).scalar_one()
        )
    return expected_count > 0 and int(version_rows[0].node_count) == expected_count


def _load_paper_input(connection: Connection, paper_row: Any) -> PaperTreeInput:
    paper_id = int(paper_row["id"])
    parse_status = str(paper_row["parse_status"])
    if parse_status == "abstract_only":
        abstract_section = (
            connection.execute(
                select(section)
                .where(
                    section.c.paper_id == paper_id,
                    section.c.section_path == "Abstract",
                )
                .order_by(section.c.id)
            )
            .mappings()
            .first()
        )
        if abstract_section is None:
            abstract = str(paper_row["abstract"] or "")
            abstract_section = (
                connection.execute(
                    insert(section)
                    .values(
                        paper_id=paper_id,
                        parent_id=None,
                        section_path="Abstract",
                        title="Abstract",
                        ordinal=0,
                        page_start=None,
                        page_end=None,
                        char_start=0,
                        char_end=len(abstract),
                        body_text=abstract,
                    )
                    .returning(section)
                )
                .mappings()
                .one()
            )
        section_rows = [abstract_section]
    else:
        section_rows = (
            connection.execute(
                select(section)
                .where(section.c.paper_id == paper_id)
                .order_by(section.c.ordinal, section.c.id)
            )
            .mappings()
            .all()
        )

    return PaperTreeInput(
        id=paper_id,
        title=str(paper_row["title"]),
        abstract=paper_row["abstract"],
        parse_status=parse_status,
        sections=tuple(
            SectionTreeInput(
                id=int(row["id"]),
                parent_id=None if row["parent_id"] is None else int(row["parent_id"]),
                section_path=str(row["section_path"]),
                title=row["title"],
                ordinal=int(row["ordinal"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
                body_text=str(row["body_text"]),
            )
            for row in section_rows
        ),
    )


def _persist_tree(
    connection: Connection,
    *,
    paper_id: int,
    nodes: list[TreeNode],
) -> None:
    connection.execute(delete(tree_node).where(tree_node.c.paper_id == paper_id))
    section_to_node: dict[int, int] = {}
    for node in nodes:
        parent_id = (
            None if node.parent_section_id is None else section_to_node[node.parent_section_id]
        )
        node_id = int(
            connection.execute(
                insert(tree_node)
                .values(
                    paper_id=node.paper_id,
                    section_id=node.section_id,
                    parent_id=parent_id,
                    node_path=node.node_path,
                    title=node.title,
                    summary=node.summary,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    depth=node.depth,
                    tree_schema_version=node.tree_schema_version,
                    summary_model=node.summary_model,
                )
                .returning(tree_node.c.id)
            ).scalar_one()
        )
        section_to_node[node.section_id] = node_id


__all__ = [
    "MAX_SUMMARY_WORDS",
    "MAX_TREE_DEPTH",
    "IndexResult",
    "PaperTreeInput",
    "SectionTreeInput",
    "TreeBuildError",
    "TreeNode",
    "UnknownScopeError",
    "build_tree",
    "index_scope",
]
