"""Temporal digests keep scholarly evidence and community attention apart."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.digest.build import CommunityMention, Digest, build_digest
from ai_researcher.digest.render import render_digest
from ai_researcher.monitor.changes import (
    ChangeSet,
    DiscourseMentionChange,
    NewEvidenceChange,
    NewPaperChange,
    ScoreMovementChange,
    StanceFlipChange,
)


def _empty_changeset() -> ChangeSet:
    return ChangeSet(
        new_papers=(),
        new_evidence=(),
        stance_flips=(),
        score_movements=(),
        discourse_mentions=(),
    )


def _populated_digest() -> Digest:
    changes = ChangeSet(
        new_papers=(NewPaperChange(paper_id=11, scope_id=1),),
        new_evidence=(NewEvidenceChange(claim_id=7, claim_evidence_id=101, stance="supports"),),
        stance_flips=(StanceFlipChange(claim_id=7, claim_evidence_id=102),),
        score_movements=(
            ScoreMovementChange(
                claim_id=7,
                confidence_before=40,
                confidence_after=70,
                confidence_delta=30,
                evidence_quality_before=55,
                evidence_quality_after=65,
                evidence_quality_delta=10,
            ),
        ),
        discourse_mentions=(
            DiscourseMentionChange(
                discourse_mention_id=501,
                paper_id=11,
                claim_id=7,
            ),
        ),
    )
    return Digest(
        since=date(2026, 8, 1),
        changes=changes,
        paper_refs={11: "Surface Codes — Results — p. 3 — arXiv: 2401.00001"},
        community=(
            CommunityMention(
                url="https://news.ycombinator.com/item?id=999",
                title="HN discussion of surface codes",
                score=128,
                num_comments=42,
                paper_id=11,
                claim_id=7,
            ),
        ),
    )


def _evidence_section(markdown: str) -> str:
    start = markdown.index("## Evidence")
    end = markdown.index("## Community attention")
    return markdown[start:end]


def _community_section(markdown: str) -> str:
    return markdown[markdown.index("## Community attention") :]


def test_render_has_exactly_two_top_level_sections() -> None:
    markdown = render_digest(_populated_digest())

    assert "## Evidence" in markdown
    assert "## Community attention" in markdown
    top_level = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert top_level == ["## Evidence", "## Community attention"]


def test_evidence_section_contains_no_attention_figures() -> None:
    markdown = render_digest(_populated_digest())
    evidence = _evidence_section(markdown)

    lowered = evidence.lower()
    assert "upvote" not in lowered
    assert "upvotes" not in lowered
    assert "num_comments" not in lowered
    assert "comments" not in lowered
    # Discourse attention score must not leak into Evidence (claim scores use other labels).
    assert "128" not in evidence
    assert "42" not in evidence
    assert "https://news.ycombinator.com" not in evidence


def test_score_movement_renders_separate_before_after_pairs() -> None:
    markdown = render_digest(_populated_digest())
    evidence = _evidence_section(markdown)

    assert "confidence: 40 → 70" in evidence
    assert "evidence_quality: 55 → 65" in evidence
    # Never a single blended delta of the two scores.
    assert "40" in evidence and "70" in evidence
    blended = 30 + 10  # confidence_delta + evidence_quality_delta
    assert f"delta: {blended}" not in evidence.lower()
    assert f"Δ {blended}" not in evidence
    assert f"delta {blended}" not in evidence.lower()


def test_community_items_link_to_original_post_not_body() -> None:
    markdown = render_digest(_populated_digest())
    community = _community_section(markdown)

    assert "[HN discussion of surface codes](https://news.ycombinator.com/item?id=999)" in community
    assert "attention is not evidence of validity" in community.lower()
    # Linked, never reproduced in full — no fabricated post body.
    assert "Lorem ipsum" not in community
    assert "full post body" not in community.lower()


def test_empty_window_produces_legible_nothing_changed_digest() -> None:
    digest = Digest(
        since=date(2026, 8, 1),
        changes=_empty_changeset(),
        paper_refs={},
        community=(),
    )
    markdown = render_digest(digest)

    assert "## Evidence" in markdown
    assert "## Community attention" in markdown
    assert "nothing changed" in markdown.lower()
    assert markdown.strip() != ""


def test_build_digest_from_injected_changeset() -> None:
    since = datetime(2026, 8, 1, tzinfo=UTC)
    changes = ChangeSet(
        new_papers=(NewPaperChange(paper_id=3, scope_id=1),),
        new_evidence=(),
        stance_flips=(),
        score_movements=(),
        discourse_mentions=(
            DiscourseMentionChange(discourse_mention_id=9, paper_id=3, claim_id=2),
        ),
    )

    def fake_detect(_since, **_kwargs):
        return changes

    def fake_enrich(_changes, **_kwargs):
        return Digest(
            since=date(2026, 8, 1),
            changes=changes,
            paper_refs={3: "Paper Three — arXiv: 2402.00002"},
            community=(
                CommunityMention(
                    url="https://reddit.com/r/QuantumComputing/comments/abc",
                    title="Reddit thread",
                    score=9,
                    num_comments=2,
                    paper_id=3,
                    claim_id=2,
                ),
            ),
        )

    digest = build_digest(
        since,
        detect_fn=fake_detect,
        enrich_fn=fake_enrich,
    )
    markdown = render_digest(digest)
    assert "Paper Three" in _evidence_section(markdown)
    assert "reddit.com" in _community_section(markdown)
    assert "9" not in _evidence_section(markdown)


def test_cli_digest_writes_file_and_stdout(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "runs"
    monkeypatch.setattr(
        "ai_researcher.digest.build.DEFAULT_DIGEST_DIR",
        output_dir,
    )

    changes = ChangeSet(
        new_papers=(NewPaperChange(paper_id=1, scope_id=1),),
        new_evidence=(),
        stance_flips=(),
        score_movements=(
            ScoreMovementChange(
                claim_id=1,
                confidence_before=10,
                confidence_after=20,
                confidence_delta=10,
                evidence_quality_before=30,
                evidence_quality_after=40,
                evidence_quality_delta=10,
            ),
        ),
        discourse_mentions=(),
    )

    def fake_detect(_since, **_kwargs):
        return changes

    monkeypatch.setattr(
        "ai_researcher.digest.build.detect_changes",
        fake_detect,
    )
    monkeypatch.setattr(
        "ai_researcher.digest.build._enrich_digest",
        lambda changes, since_date, **_kwargs: Digest(
            since=since_date,
            changes=changes,
            paper_refs={1: "Example Paper — arXiv: 2403.00003"},
            community=(),
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["digest", "--since", "2026-08-01"])
    assert result.exit_code == 0, result.output

    path = output_dir / "digest-2026-08-01.md"
    assert path.is_file()
    written = path.read_text(encoding="utf-8")
    assert written == result.output
    assert "## Evidence" in written
    assert "## Community attention" in written
    assert "confidence: 10 → 20" in written
    assert "evidence_quality: 30 → 40" in written
