"""Offline tests for topic scoping, persistence, and CLI presentation."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock

from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.sources.base import PaperRef


class FixtureSource:
    """Evidence source that serves lightweight references from an in-memory fixture."""

    def __init__(self, name: str, refs: Iterable[PaperRef]) -> None:
        self.name = name
        self.refs = tuple(refs)
        self.search_limits: list[int] = []

    def search(self, scope, limit: int) -> list[PaperRef]:
        del scope
        self.search_limits.append(limit)
        return list(self.refs[:limit])

    def fetch_metadata(self, ref: PaperRef):
        raise AssertionError(f"estimation fetched metadata for {ref.external_id}")

    def pdf_url(self, ref: PaperRef) -> str | None:
        raise AssertionError(f"estimation requested a PDF URL for {ref.external_id}")


def _scope(**overrides):
    from ai_researcher.scoping import ScopeDefinition

    values = {
        "name": "surface-codes",
        "description": "Quantum error correction with surface codes",
        "include_terms": ("quantum error correction",),
        "exclude_terms": (),
        "categories": ("quant-ph",),
        "date_from": date(2020, 1, 1),
        "date_to": date(2025, 12, 31),
        "per_source_limit": 2,
    }
    values.update(overrides)
    return ScopeDefinition(**values)


def test_estimate_uses_capped_search_results_without_fetching_papers() -> None:
    from ai_researcher.scoping.estimate import estimate_scope

    arxiv = FixtureSource(
        "arxiv",
        [
            PaperRef("arxiv", "2401.00001", title="Shared paper", doi="10.1/shared"),
            PaperRef("arxiv", "2401.00002", title="An arXiv-only paper"),
            PaperRef("arxiv", "2401.00003", title="Beyond the requested cap"),
        ],
    )
    openalex = FixtureSource(
        "openalex",
        [
            PaperRef("openalex", "W1", title="Shared paper", doi="https://doi.org/10.1/shared"),
            PaperRef("openalex", "W2", title="An OpenAlex-only paper"),
        ],
    )

    estimate = estimate_scope(_scope(), sources=(arxiv, openalex))

    assert estimate == 3
    assert arxiv.search_limits == [2]
    assert openalex.search_limits == [2]


def test_default_estimation_uses_every_registered_source(monkeypatch) -> None:
    from ai_researcher.scoping.estimate import estimate_scope
    from ai_researcher.sources import registry

    first = FixtureSource("first", [PaperRef("first", "1")])
    second = FixtureSource("second", [PaperRef("second", "2")])
    monkeypatch.setattr(registry, "_SOURCES", {"first": first, "second": second})

    assert [source.name for source in registry.registered()] == ["first", "second"]
    assert estimate_scope(_scope()) == 2


class FixtureResult:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def mappings(self):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FixtureConnection:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = [] if rows is None else rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return FixtureResult(self.rows)


def _connection_factory(connection: FixtureConnection):
    @contextmanager
    def open_connection():
        yield connection

    return open_connection


def test_scope_store_persists_and_rehydrates_scope_rows() -> None:
    from ai_researcher.scoping import store

    definition = _scope()
    write_connection = FixtureConnection()
    store.save_scope(
        definition,
        connection_factory=_connection_factory(write_connection),
    )

    assert len(write_connection.statements) == 1
    parameters = write_connection.statements[0].compile().params
    assert parameters["name"] == definition.name
    assert parameters["include_terms"] == list(definition.include_terms)
    assert parameters["exclude_terms"] == list(definition.exclude_terms)
    assert parameters["categories"] == list(definition.categories)
    assert parameters["per_source_limit"] == definition.per_source_limit

    rows = [
        {
            "name": definition.name,
            "description": definition.description,
            "include_terms": list(definition.include_terms),
            "exclude_terms": list(definition.exclude_terms),
            "categories": list(definition.categories),
            "date_from": definition.date_from,
            "date_to": definition.date_to,
            "per_source_limit": definition.per_source_limit,
        }
    ]
    read_connection = FixtureConnection(rows)
    loaded = store.load_scope(
        definition.name,
        connection_factory=_connection_factory(read_connection),
    )
    listed = store.list_scopes(
        connection_factory=_connection_factory(read_connection),
    )

    assert loaded == definition
    assert listed == [definition]


def test_dialogue_estimates_before_narrowing_and_after_each_accepted_decision() -> None:
    from ai_researcher.scoping import ScopeDefinition
    from ai_researcher.scoping.dialogue import run_dialogue

    llm_complete = Mock(
        return_value={
            "subtopics": ["surface code thresholds"],
            "adjacent_terms": ["fault-tolerant architectures"],
            "exclusions": ["biomedical sensing"],
        }
    )
    estimates = iter((120, 80, 30))
    estimated_scopes: list[ScopeDefinition] = []
    output: list[str] = []
    answers = iter((True, False, True))

    def estimate(scope: ScopeDefinition) -> int:
        estimated_scopes.append(scope)
        return next(estimates)

    narrowed = run_dialogue(
        _scope(),
        confirm=lambda prompt: (output.append(prompt), next(answers))[1],
        emit=output.append,
        complete_fn=llm_complete,
        estimate_fn=estimate,
    )

    assert llm_complete.call_args.kwargs["job"] == "scoping"
    assert llm_complete.call_args.kwargs["schema"]["required"] == [
        "subtopics",
        "adjacent_terms",
        "exclusions",
    ]
    assert estimated_scopes[0].include_terms == ("quantum error correction",)
    assert estimated_scopes[1].include_terms[-1] == "surface code thresholds"
    assert estimated_scopes[2].exclude_terms == ("biomedical sensing",)
    assert narrowed.include_terms == (
        "quantum error correction",
        "surface code thresholds",
    )
    assert narrowed.exclude_terms == ("biomedical sensing",)
    assert sum("Estimated candidates" in line for line in output) == 3
    assert "120" in next(line for line in output if "before narrowing" in line)


def test_scope_new_runs_dialogue_and_persists_exactly_one_row(
    monkeypatch,
) -> None:
    from ai_researcher.llm import gateway
    from ai_researcher.scoping import dialogue, store

    monkeypatch.setattr(
        gateway,
        "complete",
        Mock(
            return_value={
                "subtopics": ["surface code thresholds"],
                "adjacent_terms": ["fault tolerance"],
                "exclusions": ["biomedical sensing"],
            }
        ),
    )
    estimates = iter((120, 80, 60))
    monkeypatch.setattr(dialogue, "estimate_scope", lambda scope: next(estimates))
    save_scope = Mock()
    monkeypatch.setattr(store, "save_scope", save_scope)

    result = CliRunner().invoke(
        app,
        [
            "scope",
            "new",
            "surface-codes",
            "--description",
            "Quantum error correction",
            "--category",
            "quant-ph",
            "--date-from",
            "2020-01-01",
            "--date-to",
            "2025-12-31",
            "--per-source-limit",
            "50",
        ],
        input="y\nn\ny\n",
    )

    assert result.exit_code == 0, result.output
    save_scope.assert_called_once()
    saved = save_scope.call_args.args[0]
    assert saved.name == "surface-codes"
    assert saved.include_terms == (
        "Quantum error correction",
        "surface code thresholds",
    )
    assert saved.exclude_terms == ("biomedical sensing",)
    assert saved.categories == ("quant-ph",)
    assert saved.date_from == date(2020, 1, 1)
    assert saved.date_to == date(2025, 12, 31)
    assert saved.per_source_limit == 50
    assert "Estimated candidates before narrowing: 120" in result.output
    assert "Saved scope 'surface-codes'." in result.output


def test_scope_show_prints_the_full_definition_and_current_estimate(
    monkeypatch,
) -> None:
    from ai_researcher.scoping import estimate, store

    monkeypatch.setattr(store, "load_scope", lambda name: _scope(name=name))
    monkeypatch.setattr(estimate, "estimate_scope", lambda scope: 73)

    result = CliRunner().invoke(app, ["scope", "show", "surface-codes"])

    assert result.exit_code == 0, result.output
    assert "Include terms: quantum error correction" in result.output
    assert "Exclude terms: (none)" in result.output
    assert "arXiv categories: quant-ph" in result.output
    assert "Date range: 2020-01-01 to 2025-12-31" in result.output
    assert "Per-source limit: 2" in result.output
    assert "Estimated corpus size: 73" in result.output


def test_scope_list_prints_every_scope_with_its_estimated_size(
    monkeypatch,
) -> None:
    from ai_researcher.scoping import estimate, store

    scopes = [
        _scope(name="surface-codes"),
        _scope(name="logical-qubits", include_terms=("logical qubits",)),
    ]
    monkeypatch.setattr(store, "list_scopes", lambda: scopes)
    monkeypatch.setattr(
        estimate,
        "estimate_scope",
        lambda scope: {"surface-codes": 73, "logical-qubits": 41}[scope.name],
    )

    result = CliRunner().invoke(app, ["scope", "list"])

    assert result.exit_code == 0, result.output
    assert "surface-codes" in result.output
    assert "73" in result.output
    assert "logical-qubits" in result.output
    assert "41" in result.output
