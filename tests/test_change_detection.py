"""Change detection since a baseline — papers, evidence, stance, scores, discourse."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import (
    claim_evidence,
    claim_score,
    discourse_item,
    discourse_mention,
    discourse_source,
    paper,
    paper_scope,
    section,
    tree_node,
)
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import subscription as subscription_table


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
    database_name = f"test_changes_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")

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


BASELINE = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
BEFORE = BASELINE - timedelta(hours=1)
AFTER = BASELINE + timedelta(hours=1)


def _seed_scope(engine: Engine, name: str = "surface-codes") -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(scope_table)
                .values(
                    name=name,
                    description=name,
                    include_terms=[name],
                    exclude_terms=[],
                    categories=["quant-ph"],
                    per_source_limit=10,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )


def _seed_paper_with_tree(
    engine: Engine,
    *,
    title: str,
    created_at: datetime,
    scope_id: int | None = None,
) -> tuple[int, int]:
    with engine.begin() as connection:
        paper_id = int(
            connection.execute(
                insert(paper).values(title=title, created_at=created_at).returning(paper.c.id)
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE paper SET created_at = :ts WHERE id = :id"),
            {"ts": created_at, "id": paper_id},
        )
        section_id = int(
            connection.execute(
                insert(section)
                .values(
                    paper_id=paper_id,
                    section_path="Results",
                    ordinal=1,
                    body_text="body",
                )
                .returning(section.c.id)
            ).scalar_one()
        )
        tree_node_id = int(
            connection.execute(
                insert(tree_node)
                .values(
                    paper_id=paper_id,
                    section_id=section_id,
                    node_path="1",
                    summary="Summary",
                    depth=0,
                    tree_schema_version="1",
                    summary_model="test-model",
                )
                .returning(tree_node.c.id)
            ).scalar_one()
        )
        if scope_id is not None:
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))
    return paper_id, tree_node_id


def _seed_claim(
    engine: Engine,
    *,
    paper_id: int,
    tree_node_id: int,
    claim_text: str = "Threshold is 1%",
) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(claim_table)
                .values(
                    paper_id=paper_id,
                    tree_node_id=tree_node_id,
                    claim_text=claim_text,
                    normalized_text=claim_text.lower(),
                    claim_type="quantitative",
                    extraction_model="test-model",
                    prompt_version="1",
                )
                .returning(claim_table.c.id)
            ).scalar_one()
        )


def _subscribe_topic(engine: Engine, scope_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(subscription_table).values(
                kind="topic",
                scope_id=scope_id,
                claim_id=None,
                active=True,
            )
        )


def _subscribe_claim(engine: Engine, claim_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(subscription_table).values(
                kind="claim",
                scope_id=None,
                claim_id=claim_id,
                active=True,
            )
        )


def _add_evidence(
    engine: Engine,
    *,
    claim_id: int,
    paper_id: int,
    tree_node_id: int,
    stance: str,
    created_at: datetime,
) -> int:
    with engine.begin() as connection:
        evidence_id = int(
            connection.execute(
                insert(claim_evidence)
                .values(
                    claim_id=claim_id,
                    paper_id=paper_id,
                    tree_node_id=tree_node_id,
                    stance=stance,
                    rationale_text=f"{stance} rationale",
                    is_direct=True,
                    created_at=created_at,
                )
                .returning(claim_evidence.c.id)
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE claim_evidence SET created_at = :ts WHERE id = :id"),
            {"ts": created_at, "id": evidence_id},
        )
    return evidence_id


def _add_score(
    engine: Engine,
    *,
    claim_id: int,
    confidence: int,
    evidence_quality: int,
    scored_at: datetime,
) -> int:
    with engine.begin() as connection:
        score_id = int(
            connection.execute(
                insert(claim_score)
                .values(
                    claim_id=claim_id,
                    confidence=confidence,
                    evidence_quality=evidence_quality,
                    rubric_version="v1",
                    scored_at=scored_at,
                )
                .returning(claim_score.c.id)
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE claim_score SET scored_at = :ts WHERE id = :id"),
            {"ts": scored_at, "id": score_id},
        )
    return score_id


def _add_discourse_mention(
    engine: Engine,
    *,
    paper_id: int,
    created_at: datetime,
    external_id: str = "ext-1",
) -> int:
    with engine.begin() as connection:
        source_id = connection.execute(
            insert(discourse_source)
            .values(name=f"src-{external_id}", kind="rss", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()
        item_id = int(
            connection.execute(
                insert(discourse_item)
                .values(
                    source_id=source_id,
                    external_id=external_id,
                    url=f"https://example.com/{external_id}",
                    title="Mention",
                )
                .returning(discourse_item.c.id)
            ).scalar_one()
        )
        mention_id = int(
            connection.execute(
                insert(discourse_mention)
                .values(
                    discourse_item_id=item_id,
                    paper_id=paper_id,
                    resolved_by="arxiv",
                    created_at=created_at,
                )
                .returning(discourse_mention.c.id)
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE discourse_mention SET created_at = :ts WHERE id = :id"),
            {"ts": created_at, "id": mention_id},
        )
    return mention_id


def test_quiet_period_produces_empty_changeset(isolated_database: Engine) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database,
        title="Old paper",
        created_at=BEFORE,
        scope_id=scope_id,
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_topic(isolated_database, scope_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="supports",
        created_at=BEFORE,
    )
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=50,
        evidence_quality=50,
        scored_at=BEFORE,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert changeset.new_papers == ()
    assert changeset.new_evidence == ()
    assert changeset.stance_flips == ()
    assert changeset.score_movements == ()
    assert changeset.discourse_mentions == ()


def test_detects_new_papers_per_subscribed_scope(isolated_database: Engine) -> None:
    from ai_researcher.monitor.changes import detect_changes

    subscribed = _seed_scope(isolated_database, "surface-codes")
    other = _seed_scope(isolated_database, "other-topic")
    _subscribe_topic(isolated_database, subscribed)

    new_paper_id, _ = _seed_paper_with_tree(
        isolated_database,
        title="New in scope",
        created_at=AFTER,
        scope_id=subscribed,
    )
    _seed_paper_with_tree(
        isolated_database,
        title="New but other scope",
        created_at=AFTER,
        scope_id=other,
    )
    _seed_paper_with_tree(
        isolated_database,
        title="Old in scope",
        created_at=BEFORE,
        scope_id=subscribed,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert len(changeset.new_papers) == 1
    assert changeset.new_papers[0].paper_id == new_paper_id
    assert changeset.new_papers[0].scope_id == subscribed


def test_detects_new_claim_evidence_for_subscribed_claims(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    other_claim = _seed_claim(
        isolated_database,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        claim_text="Other claim",
    )
    _subscribe_claim(isolated_database, claim_id)

    new_evidence_id = _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="supports",
        created_at=AFTER,
    )
    _add_evidence(
        isolated_database,
        claim_id=other_claim,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="supports",
        created_at=AFTER,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert len(changeset.new_evidence) == 1
    assert changeset.new_evidence[0].claim_id == claim_id
    assert changeset.new_evidence[0].claim_evidence_id == new_evidence_id
    assert changeset.new_evidence[0].stance == "supports"


def test_first_refutes_evidence_is_reported_as_stance_flip(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="supports",
        created_at=BEFORE,
    )
    refute_id = _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="refutes",
        created_at=AFTER,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert len(changeset.stance_flips) == 1
    assert changeset.stance_flips[0].claim_id == claim_id
    assert changeset.stance_flips[0].claim_evidence_id == refute_id
    assert any(e.claim_evidence_id == refute_id for e in changeset.new_evidence)


def test_second_refutes_is_not_a_stance_flip(isolated_database: Engine) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="refutes",
        created_at=BEFORE,
    )
    _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="refutes",
        created_at=AFTER,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert changeset.stance_flips == ()
    assert len(changeset.new_evidence) == 1


def test_score_movement_reports_separate_deltas_beyond_threshold(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=40,
        evidence_quality=55,
        scored_at=BEFORE,
    )
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=60,
        evidence_quality=70,
        scored_at=AFTER,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert len(changeset.score_movements) == 1
    movement = changeset.score_movements[0]
    assert movement.claim_id == claim_id
    assert movement.confidence_before == 40
    assert movement.confidence_after == 60
    assert movement.confidence_delta == 20
    assert movement.evidence_quality_before == 55
    assert movement.evidence_quality_after == 70
    assert movement.evidence_quality_delta == 15
    # Must never surface a blended single number.
    assert not hasattr(movement, "score_delta")
    assert not hasattr(movement, "combined_delta")
    assert not hasattr(movement, "blended_delta")


def test_score_movement_below_threshold_is_ignored(isolated_database: Engine) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=50,
        evidence_quality=50,
        scored_at=BEFORE,
    )
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=55,
        evidence_quality=54,
        scored_at=AFTER,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert changeset.score_movements == ()


def test_pre_baseline_score_delta_is_not_re_reported(isolated_database: Engine) -> None:
    """Two scores both before ``since`` with |Δ| ≥ threshold must leave score_movements empty."""

    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    earlier = BEFORE - timedelta(hours=1)
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=40,
        evidence_quality=40,
        scored_at=earlier,
    )
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=70,
        evidence_quality=70,
        scored_at=BEFORE,
    )

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert changeset.score_movements == ()
    assert changeset.new_papers == ()
    assert changeset.new_evidence == ()
    assert changeset.stance_flips == ()
    assert changeset.discourse_mentions == ()


def test_score_movement_threshold_defaults_to_ten_and_is_configurable(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.config import get_settings
    from ai_researcher.monitor.changes import detect_changes

    monkeypatch.delenv("SCORE_MOVEMENT_THRESHOLD", raising=False)
    assert get_settings().score_movement_threshold == 10

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Paper", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=50,
        evidence_quality=50,
        scored_at=BEFORE,
    )
    _add_score(
        isolated_database,
        claim_id=claim_id,
        confidence=56,
        evidence_quality=50,
        scored_at=AFTER,
    )

    # Delta of 6 is below default 10.
    assert (
        detect_changes(
            BASELINE, connection_factory=_connection_factory(isolated_database)
        ).score_movements
        == ()
    )

    # Configurable threshold of 5 reports it.
    monkeypatch.setenv("SCORE_MOVEMENT_THRESHOLD", "5")
    changeset = detect_changes(
        BASELINE,
        connection_factory=_connection_factory(isolated_database),
        threshold=get_settings().score_movement_threshold,
    )
    assert len(changeset.score_movements) == 1
    assert changeset.score_movements[0].confidence_delta == 6


def test_detects_new_discourse_mentions_for_papers_backing_subscribed_claims(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.changes import detect_changes

    scope_id = _seed_scope(isolated_database)
    paper_id, tree_node_id = _seed_paper_with_tree(
        isolated_database, title="Backed paper", created_at=BEFORE, scope_id=scope_id
    )
    other_paper_id, other_tree = _seed_paper_with_tree(
        isolated_database, title="Unrelated", created_at=BEFORE, scope_id=scope_id
    )
    claim_id = _seed_claim(isolated_database, paper_id=paper_id, tree_node_id=tree_node_id)
    _subscribe_claim(isolated_database, claim_id)
    # Paper backs the subscribed claim via existing evidence.
    _add_evidence(
        isolated_database,
        claim_id=claim_id,
        paper_id=paper_id,
        tree_node_id=tree_node_id,
        stance="supports",
        created_at=BEFORE,
    )

    mention_id = _add_discourse_mention(
        isolated_database, paper_id=paper_id, created_at=AFTER, external_id="hot"
    )
    _add_discourse_mention(
        isolated_database,
        paper_id=other_paper_id,
        created_at=AFTER,
        external_id="noise",
    )
    # Silence unused tree id for clarity about the unrelated paper.
    del other_tree

    changeset = detect_changes(BASELINE, connection_factory=_connection_factory(isolated_database))

    assert len(changeset.discourse_mentions) == 1
    assert changeset.discourse_mentions[0].discourse_mention_id == mention_id
    assert changeset.discourse_mentions[0].paper_id == paper_id
    assert changeset.discourse_mentions[0].claim_id == claim_id
