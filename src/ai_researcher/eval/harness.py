"""Measure retrieval and extraction quality against a hand-labelled gold set."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select

from ai_researcher.answer import Answer
from ai_researcher.db import connect
from ai_researcher.eval.extraction_metrics import (
    ExtractedClaimObservation,
    ExtractedEvidenceObservation,
    ExtractionMetrics,
    compute_extraction_metrics,
)
from ai_researcher.eval.goldset import (
    GoldQuestion,
    PostgresSectionCatalog,
    SectionCatalog,
    load_gold_claims,
    load_goldset,
)
from ai_researcher.retrieval import TraversalResult

DEFAULT_GOLDSET_PATH = Path("eval/goldset.yaml")
DEFAULT_REPORT_DIR = Path("docs/supersaiyan/runs")
ATTRIBUTION_PATTERN = re.compile(r"\[(?:node|nodes) ([0-9]+(?:,\s*[0-9]+)*)\]\s*$")

TraverseFn = Callable[[str, str], TraversalResult]
SynthesizeFn = Callable[[str, TraversalResult], Answer]
ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """The three stable retrieval evaluation metrics."""

    recall_at_k: float
    citation_precision: float
    unsupported_statement_rate: float


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """One completed evaluation run and its persisted report location."""

    scope: str
    shortlist_backend: str
    k: int
    question_count: int
    metrics: EvaluationMetrics
    report_path: Path


@dataclass(frozen=True, slots=True)
class ExtractionEvaluationResult:
    """One completed extraction evaluation run and its report location."""

    scope: str
    claim_count: int
    metrics: ExtractionMetrics
    report_path: Path


@dataclass(frozen=True, slots=True)
class _QuestionScore:
    question: str
    gold_section_paths: tuple[str, ...]
    retrieved_section_paths: tuple[str, ...]
    cited_section_paths: tuple[str, ...]
    gold_sections_retrieved: int
    gold_sections_total: int
    gold_citations: int
    citations_total: int
    unsupported_statements: int
    statements_total: int


def run_evaluation(
    scope: str,
    *,
    k: int = 5,
    goldset_path: Path | str = DEFAULT_GOLDSET_PATH,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    traverse_fn: TraverseFn | None = None,
    synthesize_fn: SynthesizeFn | None = None,
    section_catalog: SectionCatalog | None = None,
    shortlist_backend: str | None = None,
    now: datetime | None = None,
) -> EvaluationResult:
    """Evaluate every gold question in ``scope`` and append a dated JSON run."""

    if not scope.strip():
        raise ValueError("scope must not be empty")
    if k < 1:
        raise ValueError("k must be a positive integer")

    if traverse_fn is None:
        from ai_researcher.retrieval import traverse

        traverse_fn = traverse
    if synthesize_fn is None:
        from ai_researcher.answer import synthesize

        synthesize_fn = synthesize
    if shortlist_backend is None:
        from ai_researcher.config import get_settings

        shortlist_backend = get_settings().shortlist_backend

    catalog = PostgresSectionCatalog() if section_catalog is None else section_catalog
    questions = load_goldset(
        goldset_path,
        scope=scope,
        section_catalog=catalog,
    )
    scores = tuple(
        _score_question(
            question,
            k=k,
            traversal_result=traverse_fn(question.question, scope),
            synthesize_fn=synthesize_fn,
        )
        for question in questions
    )
    metrics = _aggregate_metrics(scores)
    generated_at = _aware_now(now)
    report_path = _append_run(
        report_dir=Path(report_dir),
        generated_at=generated_at,
        run={
            "kind": "retrieval",
            "generated_at": generated_at.isoformat(),
            "scope": scope,
            "shortlist_backend": shortlist_backend,
            "k": k,
            "question_count": len(scores),
            "metrics": asdict(metrics),
            "questions": [asdict(score) for score in scores],
        },
    )
    return EvaluationResult(
        scope=scope,
        shortlist_backend=shortlist_backend,
        k=k,
        question_count=len(scores),
        metrics=metrics,
        report_path=report_path,
    )


def run_extraction_evaluation(
    scope: str,
    *,
    goldset_path: Path | str = DEFAULT_GOLDSET_PATH,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    section_catalog: SectionCatalog | None = None,
    extracted_claims: Sequence[ExtractedClaimObservation] | None = None,
    connection_factory: ConnectionFactory | None = None,
    now: datetime | None = None,
) -> ExtractionEvaluationResult:
    """Evaluate extracted claims against gold labels and append to the dated report."""

    if not scope.strip():
        raise ValueError("scope must not be empty")

    catalog = PostgresSectionCatalog() if section_catalog is None else section_catalog
    gold_claims = load_gold_claims(
        goldset_path,
        scope=scope,
        section_catalog=catalog,
    )
    observations = (
        tuple(extracted_claims)
        if extracted_claims is not None
        else load_extracted_claims(scope, connection_factory=connection_factory)
    )
    metrics = compute_extraction_metrics(gold_claims, observations)
    generated_at = _aware_now(now)
    report_path = _append_run(
        report_dir=Path(report_dir),
        generated_at=generated_at,
        run={
            "kind": "extraction",
            "generated_at": generated_at.isoformat(),
            "scope": scope,
            "claim_count": len(gold_claims),
            "extracted_count": len(observations),
            "metrics": asdict(metrics),
        },
    )
    return ExtractionEvaluationResult(
        scope=scope,
        claim_count=len(gold_claims),
        metrics=metrics,
        report_path=report_path,
    )


def load_extracted_claims(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[ExtractedClaimObservation, ...]:
    """Load extracted claims and evidence section paths for one scope from Postgres."""

    from ai_researcher.db.models import claim as claim_table
    from ai_researcher.db.models import claim_evidence as claim_evidence_table
    from ai_researcher.db.models import paper_scope, tree_node
    from ai_researcher.db.models import scope as scope_table

    factory = connect if connection_factory is None else connection_factory
    with factory() as connection:
        claim_rows = (
            connection.execute(
                select(
                    claim_table.c.id,
                    claim_table.c.normalized_text,
                    claim_table.c.object_value,
                    claim_table.c.unit,
                )
                .select_from(claim_table)
                .join(paper_scope, paper_scope.c.paper_id == claim_table.c.paper_id)
                .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                .where(
                    scope_table.c.name == scope_name,
                    claim_table.c.canonical_claim_id.is_(None),
                )
                .order_by(claim_table.c.id)
            )
            .mappings()
            .all()
        )
        if not claim_rows:
            return ()

        claim_ids = [int(row["id"]) for row in claim_rows]
        evidence_rows = (
            connection.execute(
                select(
                    claim_evidence_table.c.claim_id,
                    claim_evidence_table.c.stance,
                    tree_node.c.section_path,
                )
                .select_from(claim_evidence_table)
                .join(tree_node, tree_node.c.id == claim_evidence_table.c.tree_node_id)
                .where(claim_evidence_table.c.claim_id.in_(claim_ids))
                .order_by(claim_evidence_table.c.id)
            )
            .mappings()
            .all()
        )

    evidence_by_claim: dict[int, list[ExtractedEvidenceObservation]] = {
        claim_id: [] for claim_id in claim_ids
    }
    for row in evidence_rows:
        evidence_by_claim[int(row["claim_id"])].append(
            ExtractedEvidenceObservation(
                section_path=str(row["section_path"]),
                stance=str(row["stance"]),
            )
        )

    return tuple(
        ExtractedClaimObservation(
            id=int(row["id"]),
            normalized_text=str(row["normalized_text"]),
            object_value=None if row["object_value"] is None else float(row["object_value"]),
            unit=None if row["unit"] is None else str(row["unit"]),
            evidence=tuple(evidence_by_claim[int(row["id"])]),
        )
        for row in claim_rows
    )


def _score_question(
    question: GoldQuestion,
    *,
    k: int,
    traversal_result: TraversalResult,
    synthesize_fn: SynthesizeFn,
) -> _QuestionScore:
    answer = synthesize_fn(question.question, traversal_result)
    gold_paths = set(question.section_paths)
    retrieved_paths = tuple(node.section_path for node in traversal_result.ranked_nodes[:k])
    retrieved_gold_paths = gold_paths.intersection(retrieved_paths)
    cited_paths = tuple(citation.section_path for citation in answer.citations)
    gold_citations = sum(path in gold_paths for path in cited_paths)
    unsupported, statement_count = _unsupported_statement_counts(answer)
    return _QuestionScore(
        question=question.question,
        gold_section_paths=question.section_paths,
        retrieved_section_paths=retrieved_paths,
        cited_section_paths=cited_paths,
        gold_sections_retrieved=len(retrieved_gold_paths),
        gold_sections_total=len(gold_paths),
        gold_citations=gold_citations,
        citations_total=len(cited_paths),
        unsupported_statements=unsupported,
        statements_total=statement_count,
    )


def _unsupported_statement_counts(answer: Answer) -> tuple[int, int]:
    statements = tuple(
        line.strip() for line in (answer.answer_text or "").splitlines() if line.strip()
    )
    valid_node_ids = {citation.node_id for citation in answer.citations}
    unsupported = 0
    for statement in statements:
        match = ATTRIBUTION_PATTERN.search(statement)
        if match is None:
            unsupported += 1
            continue
        attributed_ids = {int(value.strip()) for value in match.group(1).split(",")}
        if not attributed_ids.intersection(valid_node_ids):
            unsupported += 1
    return unsupported, len(statements)


def _aggregate_metrics(scores: tuple[_QuestionScore, ...]) -> EvaluationMetrics:
    gold_retrieved = sum(score.gold_sections_retrieved for score in scores)
    gold_total = sum(score.gold_sections_total for score in scores)
    gold_citations = sum(score.gold_citations for score in scores)
    citations_total = sum(score.citations_total for score in scores)
    unsupported = sum(score.unsupported_statements for score in scores)
    statements_total = sum(score.statements_total for score in scores)
    return EvaluationMetrics(
        recall_at_k=_ratio(gold_retrieved, gold_total),
        citation_precision=_ratio(gold_citations, citations_total),
        unsupported_statement_rate=_ratio(unsupported, statements_total),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _aware_now(now: datetime | None) -> datetime:
    generated_at = datetime.now(UTC) if now is None else now
    if generated_at.tzinfo is None:
        return generated_at.replace(tzinfo=UTC)
    return generated_at


def _append_run(
    *,
    report_dir: Path,
    generated_at: datetime,
    run: dict[str, Any],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"eval-{generated_at.date().isoformat()}.json"
    if report_path.exists():
        report: dict[str, Any] = json.loads(report_path.read_text())
        if not isinstance(report.get("runs"), list):
            raise ValueError(f"Existing evaluation report is invalid: {report_path}")
    else:
        report = {
            "report_date": generated_at.date().isoformat(),
            "runs": [],
        }
    report["runs"].append(run)
    temporary_path = report_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary_path.replace(report_path)
    return report_path


__all__ = [
    "DEFAULT_GOLDSET_PATH",
    "DEFAULT_REPORT_DIR",
    "EvaluationMetrics",
    "EvaluationResult",
    "ExtractionEvaluationResult",
    "ExtractionMetrics",
    "load_extracted_claims",
    "run_evaluation",
    "run_extraction_evaluation",
]
