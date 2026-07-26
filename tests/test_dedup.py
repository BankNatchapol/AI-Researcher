"""Tests for deterministic cross-source paper identity resolution."""

from datetime import date

from ai_researcher.ingest.dedup import normalize_title, resolve_identity
from ai_researcher.sources.base import PaperMetadata


def test_normalize_title_ignores_case_punctuation_and_whitespace() -> None:
    published_title = "Attention Is All You Need"
    metadata_variant = "  Attention, is ALL you need.  "

    assert normalize_title(published_title) == normalize_title(metadata_variant)


def test_doi_match_merges_three_sources_with_three_provenance_rows() -> None:
    candidates = [
        PaperMetadata(
            source="arxiv",
            external_id="1706.03762",
            title="Attention Is All You Need",
            authors=("Ashish Vaswani",),
            published_at=date(2017, 6, 12),
            doi="10.5555/3295222.3295349",
            arxiv_id="1706.03762",
        ),
        PaperMetadata(
            source="openalex",
            external_id="W2626778328",
            title="Attention is all you need",
            authors=("Ashish Vaswani",),
            published_at=date(2017, 6, 12),
            doi="https://doi.org/10.5555/3295222.3295349",
            openalex_id="W2626778328",
        ),
        PaperMetadata(
            source="semantic_scholar",
            external_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776",
            title="Attention Is All You Need",
            authors=("Ashish Vaswani",),
            published_at=date(2017, 6, 12),
            doi="10.5555/3295222.3295349",
            s2_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        ),
    ]

    merged = resolve_identity(candidates)

    assert len(merged) == 1
    assert [(row.source, row.external_id) for row in merged[0].paper_sources] == [
        ("arxiv", "1706.03762"),
        ("openalex", "W2626778328"),
        ("semantic_scholar", "204e3073870fae3d05bcbc2f6a8e263d9b72e776"),
    ]


def test_arxiv_match_is_used_when_doi_is_unavailable() -> None:
    candidates = [
        PaperMetadata(
            source="arxiv",
            external_id="2401.01234v1",
            title="Fault-tolerant quantum memories",
            arxiv_id="2401.01234v1",
        ),
        PaperMetadata(
            source="semantic_scholar",
            external_id="S2-PAPER-123",
            title="Fault tolerant quantum memories",
            arxiv_id="arXiv:2401.01234v2",
        ),
    ]

    assert len(resolve_identity(candidates)) == 1


def test_title_author_surname_and_year_match_is_the_final_fallback() -> None:
    candidates = [
        PaperMetadata(
            source="openalex",
            external_id="W2626778328",
            title="Attention Is All You Need",
            authors=("Ashish Vaswani", "Noam Shazeer"),
            published_at=date(2017, 6, 12),
        ),
        PaperMetadata(
            source="semantic_scholar",
            external_id="S2-ATTENTION",
            title="  Attention, is ALL you need.  ",
            authors=("Vaswani, Ashish",),
            published_at=date(2017, 12, 1),
        ),
    ]

    assert len(resolve_identity(candidates)) == 1


def test_merging_fills_empty_fields_without_overwriting_existing_values() -> None:
    candidates = [
        PaperMetadata(
            source="arxiv",
            external_id="1706.03762",
            title="Attention Is All You Need",
            abstract="Canonical abstract from the first source.",
            authors=("Ashish Vaswani",),
            published_at=date(2017, 6, 12),
            arxiv_id="1706.03762",
            is_preprint=True,
        ),
        PaperMetadata(
            source="openalex",
            external_id="W2626778328",
            title="Attention is all you need",
            abstract="A later abstract must not replace the first.",
            authors=("Vaswani, Ashish",),
            published_at=date(2017, 12, 1),
            venue="NeurIPS",
            doi="10.5555/3295222.3295349",
            arxiv_id="1706.03762v5",
            openalex_id="W2626778328",
            pdf_url="https://example.org/attention.pdf",
        ),
    ]

    paper = resolve_identity(candidates)[0]

    assert paper.title == "Attention Is All You Need"
    assert paper.abstract == "Canonical abstract from the first source."
    assert paper.authors == ("Ashish Vaswani",)
    assert paper.published_at == date(2017, 6, 12)
    assert paper.venue == "NeurIPS"
    assert paper.doi == "10.5555/3295222.3295349"
    assert paper.openalex_id == "W2626778328"
    assert paper.pdf_url == "https://example.org/attention.pdf"
    assert paper.is_preprint is True


def test_different_non_null_dois_never_merge_by_title() -> None:
    candidates = [
        PaperMetadata(
            source="openalex",
            external_id="W-FIRST",
            title="A shared catalog title",
            authors=("Ada Researcher",),
            published_at=date(2024, 1, 1),
            doi="10.1000/first",
        ),
        PaperMetadata(
            source="semantic_scholar",
            external_id="S2-SECOND",
            title="A shared catalog title",
            authors=("Ada Researcher",),
            published_at=date(2024, 5, 1),
            doi="10.1000/second",
        ),
    ]

    assert len(resolve_identity(candidates)) == 2


def test_near_miss_title_prefix_stays_as_two_distinct_papers() -> None:
    candidates = [
        PaperMetadata(
            source="openalex",
            external_id="W-ATTENTION",
            title="Attention Is All You Need",
            authors=("Ashish Vaswani",),
            published_at=date(2017, 6, 12),
        ),
        PaperMetadata(
            source="semantic_scholar",
            external_id="S2-PURE-ATTENTION",
            title=(
                "Attention Is Not All You Need: Pure Attention Loses Rank "
                "Doubly Exponentially with Depth"
            ),
            authors=("Yihe Dong",),
            published_at=date(2021, 1, 1),
        ),
    ]

    assert len(resolve_identity(candidates)) == 2
