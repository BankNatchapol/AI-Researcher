"""Evidence sweep: subscribed scopes through ingest → tree → extract → link → rescore."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, func, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import (
    claim,
    claim_evidence,
    paper,
    paper_scope,
    section,
    sweep_run,
    tree_node,
)
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import subscription as subscription_table
from ai_researcher.ingest.acquire import AcquisitionPaper, AcquisitionResult
from ai_researcher.ingest.dedup import MergedPaper, PaperSource
from ai_researcher.ingest.parse import ParsePaper, ParseResult
from ai_researcher.ingest.tei import SectionRecord
from ai_researcher.scoping import ScopeDefinition

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_TEI = (FIXTURES / "sample-paper.tei.xml").read_text(encoding="utf-8")


def _pg8000_url(url: str):
    return make_url(url).set(drivername="postgresql+pg8000")


@pytest.fixture
def database_url() -> str:
    url = os.environ.get(
        "AI_RESEARCHER_TEST_DATABASE_URL",
        os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:issue3@127.0.0.1:55432/ai_researcher_test",
        ),
    )
    engine = create_engine(_pg8000_url(url), connect_args={"timeout": 2})
    try:
        with engine.connect():
            pass
    except SQLAlchemyError:
        pytest.skip("PostgreSQL test database is unavailable")
    finally:
        engine.dispose()
    return url


@pytest.fixture
def isolated_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    database_name = f"test_evidence_sweep_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("ARXIV_MIN_INTERVAL_SECONDS", "0")

    from ai_researcher.db.migrate import migrate

    migrate()

    try:
        yield database_engine
    finally:
        database_engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def _connection_factory(engine: Engine):
    @contextmanager
    def open_connection():
        with engine.begin() as connection:
            yield connection

    return open_connection


def _scope(**overrides) -> ScopeDefinition:
    values = {
        "name": "surface-codes",
        "description": "Quantum error correction with surface codes",
        "include_terms": ("quantum error correction",),
        "exclude_terms": (),
        "categories": ("quant-ph",),
        "date_from": date(2020, 1, 1),
        "date_to": date(2025, 12, 31),
        "per_source_limit": 10,
    }
    values.update(overrides)
    return ScopeDefinition(**values)


def _insert_scope(engine: Engine, definition: ScopeDefinition) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(scope_table)
                .values(
                    name=definition.name,
                    description=definition.description,
                    include_terms=list(definition.include_terms),
                    exclude_terms=list(definition.exclude_terms),
                    categories=list(definition.categories),
                    date_from=definition.date_from,
                    date_to=definition.date_to,
                    per_source_limit=definition.per_source_limit,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )


def _subscribe_topic(engine: Engine, scope_id: int) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(subscription_table)
                .values(kind="topic", scope_id=scope_id, claim_id=None, active=True)
                .returning(subscription_table.c.id)
            ).scalar_one()
        )


def _one_paper_fixture() -> MergedPaper:
    return MergedPaper(
        title="Surface code threshold paper",
        abstract="We report a 1% threshold.",
        authors=("Ada Lovelace",),
        published_at=date(2024, 1, 1),
        arxiv_id="2401.00001",
        is_preprint=True,
        pdf_url="https://example.test/paper.pdf",
        paper_sources=(PaperSource(source="arxiv", external_id="2401.00001"),),
    )


def _install_ingest_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    discover_fn=None,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.sources import registry

    def default_discover(scope, **kwargs):
        del scope, kwargs
        return [_one_paper_fixture()]

    def fake_acquire(paper_obj: AcquisitionPaper, **kwargs) -> AcquisitionResult:
        del kwargs
        paper_obj.pdf_path = "/tmp/fixture.pdf"
        paper_obj.oa_status = "oa"
        paper_obj.parse_status = "downloaded"
        return AcquisitionResult(paper_id=paper_obj.id, status="downloaded", error=None)

    def fake_parse(paper_obj: ParsePaper, **kwargs) -> ParseResult:
        del kwargs
        paper_obj.tei_xml = SAMPLE_TEI
        paper_obj.parse_status = "parsed"
        return ParseResult(
            paper_id=paper_obj.id,
            status="parsed",
            error=None,
            sections=[
                SectionRecord(
                    id=1,
                    parent_id=None,
                    section_path="1",
                    title="Results",
                    ordinal=0,
                    page_start=1,
                    page_end=2,
                    char_start=0,
                    char_end=20,
                    body_text="The surface-code threshold is approximately 1 percent.",
                ),
            ],
        )

    monkeypatch.setattr(pipeline, "discover_candidates", discover_fn or default_discover)
    monkeypatch.setattr(pipeline, "acquire_pdf", fake_acquire)
    monkeypatch.setattr(pipeline, "parse_pdf", fake_parse)
    monkeypatch.setattr(registry, "_SOURCES", {})


def _install_downstream_stubs(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    *,
    fail_extract_for: set[int] | None = None,
) -> dict[str, list]:
    """Stub tree/extract/link/score while writing the rows ACs assert on."""

    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline as extraction_pipeline
    from ai_researcher.scoring import confidence as confidence_scoring
    from ai_researcher.trees import build as tree_build

    fail_extract_for = fail_extract_for or set()
    calls: dict[str, list] = {"index": [], "extract": [], "link": [], "score": []}

    def fake_index(scope_name: str, **kwargs):
        del kwargs
        calls["index"].append(scope_name)
        with engine.begin() as connection:
            section_rows = (
                connection.execute(
                    select(
                        paper.c.id.label("paper_id"),
                        section.c.id.label("section_id"),
                    )
                    .join(paper_scope, paper_scope.c.paper_id == paper.c.id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .join(section, section.c.paper_id == paper.c.id)
                    .where(scope_table.c.name == scope_name)
                    .order_by(paper.c.id, section.c.id)
                )
                .mappings()
                .all()
            )
            paper_ids = {int(row["paper_id"]) for row in section_rows}
            if paper_ids:
                connection.execute(delete(tree_node).where(tree_node.c.paper_id.in_(paper_ids)))
            for row in section_rows:
                connection.execute(
                    insert(tree_node).values(
                        paper_id=int(row["paper_id"]),
                        section_id=int(row["section_id"]),
                        parent_id=None,
                        node_path="1",
                        title="Results",
                        summary="Surface-code threshold around one percent.",
                        page_start=1,
                        page_end=2,
                        depth=0,
                        tree_schema_version="1",
                        summary_model="codex",
                    )
                )
        return tree_build.IndexResult(built=len(section_rows), skipped=0, failed=0)

    def fake_extract(scope_name: str, **kwargs):
        del kwargs
        calls["extract"].append(scope_name)
        results = []
        with engine.begin() as connection:
            papers = (
                connection.execute(
                    select(paper.c.id)
                    .join(paper_scope, paper_scope.c.paper_id == paper.c.id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .where(scope_table.c.name == scope_name)
                    .order_by(paper.c.id)
                )
                .scalars()
                .all()
            )
            extracted = skipped = failed = 0
            for raw_paper_id in papers:
                paper_id = int(raw_paper_id)
                if paper_id in fail_extract_for:
                    failed += 1
                    results.append(
                        extraction_pipeline.ExtractionResult(
                            paper_id=paper_id,
                            failed=True,
                            failure_reason="injected extract failure",
                        )
                    )
                    continue
                node_id = connection.execute(
                    select(tree_node.c.id).where(tree_node.c.paper_id == paper_id).limit(1)
                ).scalar_one_or_none()
                if node_id is None:
                    skipped += 1
                    results.append(
                        extraction_pipeline.ExtractionResult(paper_id=paper_id, skipped=True)
                    )
                    continue
                existing = connection.execute(
                    select(func.count()).select_from(claim).where(claim.c.paper_id == paper_id)
                ).scalar_one()
                if int(existing) > 0:
                    skipped += 1
                    results.append(
                        extraction_pipeline.ExtractionResult(paper_id=paper_id, skipped=True)
                    )
                    continue
                connection.execute(
                    insert(claim).values(
                        paper_id=paper_id,
                        tree_node_id=int(node_id),
                        claim_text="The threshold is 1%",
                        normalized_text="the threshold is 1%",
                        claim_type="fact",
                        extraction_model="codex",
                        prompt_version="1",
                    )
                )
                extracted += 1
                results.append(extraction_pipeline.ExtractionResult(paper_id=paper_id, claims=1))
        return extraction_pipeline.ExtractScopeResult(
            extracted=extracted,
            skipped=skipped,
            failed=failed,
            papers=tuple(results),
        )

    def fake_link(scope_name: str, **kwargs):
        del kwargs
        calls["link"].append(scope_name)
        with engine.begin() as connection:
            rows = (
                connection.execute(
                    select(
                        claim.c.id,
                        claim.c.paper_id,
                        tree_node.c.id.label("node_id"),
                    )
                    .join(paper_scope, paper_scope.c.paper_id == claim.c.paper_id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .join(tree_node, tree_node.c.paper_id == claim.c.paper_id)
                    .outerjoin(
                        claim_evidence,
                        claim_evidence.c.claim_id == claim.c.id,
                    )
                    .where(
                        scope_table.c.name == scope_name,
                        claim_evidence.c.id.is_(None),
                    )
                    .order_by(claim.c.id)
                )
                .mappings()
                .all()
            )
            linked = 0
            for row in rows:
                connection.execute(
                    insert(claim_evidence).values(
                        claim_id=int(row["id"]),
                        paper_id=int(row["paper_id"]),
                        tree_node_id=int(row["node_id"]),
                        stance="supports",
                        rationale_text="The surface-code threshold is approximately 1 percent.",
                        is_direct=True,
                    )
                )
                linked += 1
        return evidence_link.EvidenceLinkScopeResult(
            claims_linked=linked,
            evidence_links=linked,
            failed=0,
        )

    def fake_score(scope_name: str, **kwargs):
        del kwargs
        calls["score"].append(scope_name)
        return confidence_scoring.ConfidenceScopeResult(scored=1, failed=0, scores=())

    monkeypatch.setattr(tree_build, "index_scope", fake_index)
    monkeypatch.setattr(extraction_pipeline, "extract_scope", fake_extract)
    monkeypatch.setattr(evidence_link, "link_scope_evidence", fake_link)
    monkeypatch.setattr(confidence_scoring, "score_scope_confidence", fake_score)
    return calls


def test_new_paper_sweep_writes_run_and_processes_end_to_end(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.monitor import sweep

    definition = _scope()
    scope_id = _insert_scope(isolated_database, definition)
    _subscribe_topic(isolated_database, scope_id)
    _install_ingest_fakes(monkeypatch)
    downstream = _install_downstream_stubs(monkeypatch, isolated_database)

    result = sweep.run_evidence_sweep(
        connection_factory=_connection_factory(isolated_database),
    )

    assert result.kind == "evidence"
    assert result.state in {"completed", "completed_with_errors"}
    assert result.items_found == 1

    with isolated_database.connect() as connection:
        runs = connection.execute(select(sweep_run)).mappings().all()
        papers = connection.execute(select(paper)).mappings().all()
        nodes = connection.execute(select(tree_node)).mappings().all()
        claims = connection.execute(select(claim)).mappings().all()
        evidence = connection.execute(select(claim_evidence)).mappings().all()

    assert len(runs) == 1
    assert runs[0]["kind"] == "evidence"
    assert runs[0]["items_found"] == 1
    assert runs[0]["state"] in {"completed", "completed_with_errors"}
    assert runs[0]["finished_at"] is not None
    assert len(papers) == 1
    assert len(nodes) >= 1
    assert len(claims) >= 1
    assert len(evidence) >= 1
    assert downstream["index"] == [definition.name]
    assert downstream["extract"] == [definition.name]
    assert downstream["link"] == [definition.name]
    assert downstream["score"] == [definition.name]


def test_empty_rerun_creates_zero_new_papers_and_exits_zero(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.monitor import sweep

    definition = _scope()
    scope_id = _insert_scope(isolated_database, definition)
    _subscribe_topic(isolated_database, scope_id)
    _install_ingest_fakes(monkeypatch)
    _install_downstream_stubs(monkeypatch, isolated_database)

    first = sweep.run_evidence_sweep(connection_factory=_connection_factory(isolated_database))
    assert first.items_found == 1

    with isolated_database.connect() as connection:
        paper_count_after_first = connection.execute(
            select(func.count()).select_from(paper)
        ).scalar_one()

    second = sweep.run_evidence_sweep(connection_factory=_connection_factory(isolated_database))
    assert second.state in {"completed", "completed_with_errors"}
    assert second.items_found == 0

    with isolated_database.connect() as connection:
        paper_count_after_second = connection.execute(
            select(func.count()).select_from(paper)
        ).scalar_one()
        runs = connection.execute(select(sweep_run)).mappings().all()

    assert paper_count_after_second == paper_count_after_first
    assert len(runs) == 2
    assert runs[-1]["items_found"] == 0

    runner = CliRunner()
    cli = runner.invoke(app, ["sweep", "--kind", "evidence"])
    assert cli.exit_code == 0, cli.output


def test_ceiling_refusal_logs_and_stops_adding_papers(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_researcher.ingest.pipeline import CORPUS_CEILING
    from ai_researcher.monitor import sweep

    definition = _scope()
    scope_id = _insert_scope(isolated_database, definition)
    _subscribe_topic(isolated_database, scope_id)

    with isolated_database.begin() as connection:
        for index in range(CORPUS_CEILING):
            paper_id = int(
                connection.execute(
                    insert(paper)
                    .values(title=f"Existing {index}", arxiv_id=f"2301.{index:05d}")
                    .returning(paper.c.id)
                ).scalar_one()
            )
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))

    ingest_calls: list[str] = []

    def forbidden_ingest(scope_name: str, **kwargs):
        del kwargs
        ingest_calls.append(scope_name)
        raise AssertionError("ceiling refusal must not call ingest")

    with caplog.at_level(logging.INFO):
        result = sweep.run_evidence_sweep(
            connection_factory=_connection_factory(isolated_database),
            ingest_fn=forbidden_ingest,
        )

    assert result.state in {"completed", "completed_with_errors"}
    assert result.items_found == 0
    assert ingest_calls == []
    assert any(
        "1000" in record.getMessage() and "ceiling" in record.getMessage().lower()
        for record in caplog.records
    )

    with isolated_database.connect() as connection:
        count = connection.execute(
            select(func.count()).select_from(paper_scope).where(paper_scope.c.scope_id == scope_id)
        ).scalar_one()
        runs = connection.execute(select(sweep_run)).mappings().all()

    assert int(count) == CORPUS_CEILING
    assert len(runs) == 1
    assert runs[0]["kind"] == "evidence"
    assert runs[0]["items_found"] == 0


def test_per_paper_failure_does_not_abort_sweep(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.monitor import sweep

    good = _scope(name="good-scope")
    bad = _scope(name="bad-scope")
    good_id = _insert_scope(isolated_database, good)
    bad_id = _insert_scope(isolated_database, bad)
    _subscribe_topic(isolated_database, good_id)
    _subscribe_topic(isolated_database, bad_id)

    def selective_discover(scope, **kwargs):
        del kwargs
        if getattr(scope, "name", None) == "good-scope":
            return [_one_paper_fixture()]
        return []

    _install_ingest_fakes(monkeypatch, discover_fn=selective_discover)
    _install_downstream_stubs(monkeypatch, isolated_database)

    def ingest_wrapper(scope_name: str, **kwargs):
        if scope_name == "bad-scope":
            raise RuntimeError("injected scope failure")
        return sweep._default_ingest(scope_name, **kwargs)

    result = sweep.run_evidence_sweep(
        connection_factory=_connection_factory(isolated_database),
        ingest_fn=ingest_wrapper,
    )

    assert result.items_found >= 1
    assert result.error is not None
    assert "injected scope failure" in result.error or "bad-scope" in result.error
    assert result.state in {"completed_with_errors", "failed", "completed"}

    with isolated_database.connect() as connection:
        papers = connection.execute(select(paper)).mappings().all()
        claims = connection.execute(select(claim)).mappings().all()
        runs = connection.execute(select(sweep_run)).mappings().all()

    assert len(papers) >= 1
    assert len(claims) >= 1
    assert len(runs) == 1
    assert runs[0]["finished_at"] is not None


def test_cli_sweep_kind_evidence_exits_zero(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.monitor import sweep

    definition = _scope()
    scope_id = _insert_scope(isolated_database, definition)
    _subscribe_topic(isolated_database, scope_id)

    def fake_run(**kwargs):
        del kwargs
        return sweep.SweepResult(
            sweep_run_id=1,
            kind="evidence",
            state="completed",
            items_found=0,
            error=None,
        )

    monkeypatch.setattr(sweep, "run_evidence_sweep", fake_run)
    runner = CliRunner()
    result = runner.invoke(app, ["sweep", "--kind", "evidence"])
    assert result.exit_code == 0, result.output
    assert "evidence" in result.output.lower()
