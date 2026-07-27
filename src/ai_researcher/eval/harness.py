"""Measure retrieval and citation quality against a hand-labelled gold set."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_researcher.answer import Answer
from ai_researcher.eval.goldset import (
    GoldQuestion,
    PostgresSectionCatalog,
    SectionCatalog,
    load_goldset,
)
from ai_researcher.retrieval import TraversalResult

DEFAULT_GOLDSET_PATH = Path("eval/goldset.yaml")
DEFAULT_REPORT_DIR = Path("docs/supersaiyan/runs")
ATTRIBUTION_PATTERN = re.compile(r"\[(?:node|nodes) ([0-9]+(?:,\s*[0-9]+)*)\]\s*$")

TraverseFn = Callable[[str, str], TraversalResult]
SynthesizeFn = Callable[[str, TraversalResult], Answer]


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
    generated_at = datetime.now(UTC) if now is None else now
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    report_path = _append_report(
        report_dir=Path(report_dir),
        generated_at=generated_at,
        scope=scope,
        shortlist_backend=shortlist_backend,
        k=k,
        metrics=metrics,
        scores=scores,
    )
    return EvaluationResult(
        scope=scope,
        shortlist_backend=shortlist_backend,
        k=k,
        question_count=len(scores),
        metrics=metrics,
        report_path=report_path,
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


def _append_report(
    *,
    report_dir: Path,
    generated_at: datetime,
    scope: str,
    shortlist_backend: str,
    k: int,
    metrics: EvaluationMetrics,
    scores: tuple[_QuestionScore, ...],
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
    report["runs"].append(
        {
            "generated_at": generated_at.isoformat(),
            "scope": scope,
            "shortlist_backend": shortlist_backend,
            "k": k,
            "question_count": len(scores),
            "metrics": asdict(metrics),
            "questions": [asdict(score) for score in scores],
        }
    )
    temporary_path = report_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary_path.replace(report_path)
    return report_path


__all__ = [
    "DEFAULT_GOLDSET_PATH",
    "DEFAULT_REPORT_DIR",
    "EvaluationMetrics",
    "EvaluationResult",
    "run_evaluation",
]
