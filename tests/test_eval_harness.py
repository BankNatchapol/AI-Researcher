"""End-to-end tests for the offline retrieval evaluation harness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_researcher.answer import Answer, Citation
from ai_researcher.cli import app
from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "eval-corpus"
runner = CliRunner()


@dataclass(frozen=True)
class FixtureSectionCatalog:
    """Expose the committed fixture's known paths without a database."""

    corpus: dict

    def section_paths(self, scope: str) -> frozenset[str]:
        records = self.corpus["scopes"].get(scope, {}).get("sections", [])
        return frozenset(record["section_path"] for record in records)


class FixtureResearchCore:
    """Run deterministic traversal and synthesis over the committed fixture corpus."""

    def __init__(self, corpus: dict) -> None:
        self._scopes = corpus["scopes"]
        self._nodes_by_id = {
            scope: {
                record["node_id"]: RankedNode(
                    node_id=record["node_id"],
                    paper_id=record["paper_id"],
                    section_path=record["section_path"],
                    title=record["section_path"].rsplit("/", 1)[-1],
                    summary=f"Fixture evidence from {record['section_path']}.",
                    page_start=record["page_start"],
                    page_end=record["page_end"],
                    relevance=100 - index,
                    reason="Committed offline fixture ranking.",
                )
                for index, record in enumerate(payload["sections"])
            }
            for scope, payload in self._scopes.items()
        }

    def traverse(
        self,
        question: str,
        scope: str,
        max_nodes: int | None = None,
    ) -> TraversalResult:
        del max_nodes
        question_fixture = self._scopes[scope]["questions"][question]
        nodes = tuple(
            self._nodes_by_id[scope][node_id] for node_id in question_fixture["retrieved_node_ids"]
        )
        return TraversalResult(
            ranked_nodes=nodes,
            trace=TraversalTrace(
                expanded_nodes=(),
                selected_node_ids=tuple(node.node_id for node in nodes),
                stopped_reason="sufficient_evidence",
            ),
        )

    def synthesize(self, question: str, traversal_result: TraversalResult) -> Answer:
        scope = next(
            scope for scope, payload in self._scopes.items() if question in payload["questions"]
        )
        question_fixture = self._scopes[scope]["questions"][question]
        nodes_by_id = {node.node_id: node for node in traversal_result.ranked_nodes}
        citations = [
            Citation(
                node_id=node_id,
                paper_id=nodes_by_id[node_id].paper_id,
                paper_title=f"Fixture paper {nodes_by_id[node_id].paper_id}",
                section_path=nodes_by_id[node_id].section_path,
                page_start=nodes_by_id[node_id].page_start,
                page_end=nodes_by_id[node_id].page_end,
                identifier_type="doi",
                identifier=f"10.0000/fixture-{nodes_by_id[node_id].paper_id}",
            )
            for node_id in question_fixture["cited_node_ids"]
        ]
        rendered_statements = []
        for statement in question_fixture["statements"]:
            node_ids = statement["node_ids"]
            if not node_ids:
                rendered_statements.append(statement["text"])
            else:
                label = "node" if len(node_ids) == 1 else "nodes"
                rendered_statements.append(
                    f"{statement['text']} [{label} {', '.join(map(str, node_ids))}]"
                )
        return Answer(
            answer_text="\n".join(rendered_statements),
            citations=citations,
            budget_limited=False,
            insufficient_evidence=False,
        )


@pytest.fixture
def fixture_corpus() -> dict:
    return json.loads((FIXTURE_DIR / "corpus.json").read_text())


def test_default_goldset_has_twenty_questions_across_quantum_and_ai() -> None:
    from ai_researcher.eval.goldset import load_goldset

    questions = load_goldset(Path("eval/goldset.yaml"))

    assert len(questions) >= 20
    assert {question.scope for question in questions} >= {"surface-codes", "transformers"}
    assert all(question.question and question.section_paths for question in questions)


def test_goldset_fails_loudly_when_a_path_matches_no_known_section(
    fixture_corpus: dict,
    tmp_path: Path,
) -> None:
    from ai_researcher.eval.goldset import GoldSetValidationError, load_goldset

    bad_goldset = tmp_path / "bad-goldset.yaml"
    bad_goldset.write_text(
        "\n".join(
            [
                "version: 1",
                "questions:",
                "  - question: Where is the missing evidence?",
                "    scope: fixture-eval",
                "    section_paths:",
                "      - Results/Does Not Exist",
            ]
        )
    )

    with pytest.raises(GoldSetValidationError, match="Results/Does Not Exist"):
        load_goldset(
            bad_goldset,
            scope="fixture-eval",
            section_catalog=FixtureSectionCatalog(fixture_corpus),
        )


def test_harness_runs_end_to_end_offline_and_appends_comparable_backend_runs(
    fixture_corpus: dict,
    tmp_path: Path,
) -> None:
    from ai_researcher.eval.harness import run_evaluation

    core = FixtureResearchCore(fixture_corpus)
    fixed_time = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
    common = {
        "scope": "fixture-eval",
        "goldset_path": FIXTURE_DIR / "goldset.yaml",
        "report_dir": tmp_path,
        "k": 1,
        "traverse_fn": core.traverse,
        "synthesize_fn": core.synthesize,
        "section_catalog": FixtureSectionCatalog(fixture_corpus),
        "now": fixed_time,
    }

    pageindex = run_evaluation(shortlist_backend="pageindex", **common)
    postgres = run_evaluation(shortlist_backend="postgres_fts", **common)

    assert pageindex.metrics.recall_at_k == pytest.approx(0.5)
    assert pageindex.metrics.citation_precision == pytest.approx(0.5)
    assert pageindex.metrics.unsupported_statement_rate == pytest.approx(1 / 3)
    assert postgres.metrics == pageindex.metrics
    assert pageindex.report_path == tmp_path / "eval-2026-07-27.json"
    report = json.loads(pageindex.report_path.read_text())
    assert [run["shortlist_backend"] for run in report["runs"]] == [
        "pageindex",
        "postgres_fts",
    ]
    assert report["runs"][0]["metrics"] == report["runs"][1]["metrics"]
    assert report["runs"][0]["question_count"] == 2


def test_eval_cli_reports_all_metrics_and_report_path(monkeypatch, tmp_path: Path) -> None:
    import ai_researcher.eval
    from ai_researcher.eval import EvaluationMetrics, EvaluationResult

    report_path = tmp_path / "eval-2026-07-27.json"
    calls: list[tuple[str, int]] = []

    def fake_run(scope: str, *, k: int) -> EvaluationResult:
        calls.append((scope, k))
        return EvaluationResult(
            scope=scope,
            shortlist_backend="pageindex",
            k=k,
            question_count=10,
            metrics=EvaluationMetrics(
                recall_at_k=0.8,
                citation_precision=0.75,
                unsupported_statement_rate=0.1,
            ),
            report_path=report_path,
        )

    monkeypatch.setattr(ai_researcher.eval, "run_evaluation", fake_run)

    result = runner.invoke(app, ["eval", "--scope", "surface-codes", "--k", "5"])

    assert result.exit_code == 0, result.output
    assert calls == [("surface-codes", 5)]
    assert "retrieval recall@5: 0.800" in result.stdout
    assert "citation precision: 0.750" in result.stdout
    assert "unsupported-statement rate: 0.100" in result.stdout
    assert str(report_path) in result.stdout
