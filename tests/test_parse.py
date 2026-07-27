"""Offline tests for GROBID PDF parsing and TEI section normalization."""

from __future__ import annotations

import importlib
from pathlib import Path
from urllib.error import URLError

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_TEI = FIXTURES / "sample-paper.tei.xml"
SAMPLE_PDF = FIXTURES / "sample.pdf"
SAMPLE_GROBID_PDF = FIXTURES / "sample-grobid.pdf"

EXPECTED_SECTION_TITLES = [
    "Introduction",
    "Methods",
    "Noise model",
    "Decoder",
    "Results",
    "Threshold estimates",
    "Untitled section 1",
    "Conclusion",
]

EXPECTED_SECTION_PATHS = [
    "Introduction",
    "Methods",
    "Methods/Noise model",
    "Methods/Decoder",
    "Results",
    "Results/Threshold estimates",
    "Results/Threshold estimates/Untitled section 1",
    "Conclusion",
]


def _parse_module():
    try:
        return importlib.import_module("ai_researcher.ingest.parse")
    except ModuleNotFoundError:
        pytest.fail("ai_researcher.ingest.parse has not been implemented")


def _tei_module():
    try:
        return importlib.import_module("ai_researcher.ingest.tei")
    except ModuleNotFoundError:
        pytest.fail("ai_researcher.ingest.tei has not been implemented")


@pytest.fixture(autouse=True)
def application_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")


def test_tei_fixture_produces_expected_nested_section_titles_in_order() -> None:
    tei = _tei_module()
    assert hasattr(tei, "tei_to_sections")
    assert hasattr(tei, "SectionRecord")

    sections = tei.tei_to_sections(SAMPLE_TEI.read_text(encoding="utf-8"))

    assert [section.title for section in sections] == EXPECTED_SECTION_TITLES
    assert [section.section_path for section in sections] == EXPECTED_SECTION_PATHS
    assert [section.ordinal for section in sections] == list(range(len(sections)))

    by_path = {section.section_path: section for section in sections}
    introduction = by_path["Introduction"]
    methods = by_path["Methods"]
    noise_model = by_path["Methods/Noise model"]
    threshold = by_path["Results/Threshold estimates"]
    untitled = by_path["Results/Threshold estimates/Untitled section 1"]

    assert introduction.parent_id is None
    assert methods.parent_id is None
    assert noise_model.parent_id == methods.id
    assert threshold.parent_id == by_path["Results"].id
    assert untitled.parent_id == threshold.id

    assert introduction.page_start == 1
    assert introduction.page_end == 1
    assert methods.page_start == 2
    assert methods.page_end == 2
    assert by_path["Methods/Decoder"].page_start == 3
    assert threshold.page_start == 4
    assert untitled.page_start == 5
    assert by_path["Conclusion"].page_start == 6

    assert "Fault-tolerant quantum computing" in introduction.body_text
    assert "Independent X and Z errors" in noise_model.body_text
    assert "surface-code threshold" in by_path["Conclusion"].body_text
    assert "Independent X and Z errors" not in methods.body_text
    assert "Supplemental curves" in untitled.body_text
    assert "Supplemental curves" not in threshold.body_text

    assert introduction.char_start == 0
    assert introduction.char_end == len(introduction.body_text)
    assert introduction.body_text[introduction.char_start : introduction.char_end] == (
        introduction.body_text
    )
    assert noise_model.char_start == 0
    assert noise_model.char_end == len(noise_model.body_text)


def test_tei_page_range_uses_every_coordinate_group_in_a_paragraph() -> None:
    tei = _tei_module()
    tei_xml = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <text>
        <body>
          <div>
            <head>Cross-page result</head>
            <p coords="4,72,700,400,12;5,72,80,400,12">
              This paragraph continues onto the next page.
            </p>
          </div>
        </body>
      </text>
    </TEI>
    """

    section = tei.tei_to_sections(tei_xml)[0]

    assert section.page_start == 4
    assert section.page_end == 5


def test_parse_pdf_stores_tei_and_sections_from_grobid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parse = _parse_module()
    assert hasattr(parse, "ParsePaper")
    assert hasattr(parse, "parse_pdf")

    tei_xml = SAMPLE_TEI.read_text(encoding="utf-8")
    pdf_path = tmp_path / "42.pdf"
    pdf_path.write_bytes(SAMPLE_PDF.read_bytes())
    paper = parse.ParsePaper(id=42, pdf_path=str(pdf_path))
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_process(pdf_file: Path, *, grobid_url: str, headers: dict[str, str]) -> str:
        calls.append((str(pdf_file), grobid_url, headers))
        return tei_xml

    monkeypatch.setattr(parse, "process_fulltext_document", fake_process)

    result = parse.parse_pdf(paper)

    assert result.status == "parsed"
    assert result.paper_id == 42
    assert result.error is None
    assert paper.tei_xml == tei_xml
    assert paper.parse_status == "parsed"
    assert [section.title for section in result.sections] == EXPECTED_SECTION_TITLES
    assert [section.section_path for section in result.sections] == EXPECTED_SECTION_PATHS
    assert calls == [
        (
            str(pdf_path),
            "http://localhost:8070",
            {"User-Agent": "AI-Researcher/0.1 (mailto:researcher@example.com)"},
        )
    ]


def test_grobid_failure_is_recorded_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parse = _parse_module()
    pdf_path = tmp_path / "7.pdf"
    pdf_path.write_bytes(SAMPLE_PDF.read_bytes())
    paper = parse.ParsePaper(id=7, pdf_path=str(pdf_path), tei_xml="stale", parse_status="pending")

    def boom(pdf_file: Path, *, grobid_url: str, headers: dict[str, str]) -> str:
        raise URLError("grobid refused connection")

    monkeypatch.setattr(parse, "process_fulltext_document", boom)

    result = parse.parse_pdf(paper)

    assert result.status == "failed"
    assert result.paper_id == 7
    assert result.error is not None
    assert "grobid refused connection" in result.error
    assert result.sections == []
    assert paper.parse_status == "failed"
    assert paper.tei_xml is None


def test_missing_pdf_is_recorded_as_failure_without_raising() -> None:
    parse = _parse_module()
    paper = parse.ParsePaper(id=3, pdf_path="/nonexistent/missing.pdf")

    result = parse.parse_pdf(paper)

    assert result.status == "failed"
    assert result.paper_id == 3
    assert result.error is not None
    assert result.sections == []
    assert paper.parse_status == "failed"
    assert paper.tei_xml is None


@pytest.mark.integration
def test_live_grobid_process_fulltext_when_reachable() -> None:
    parse = _parse_module()
    from ai_researcher.config import get_settings

    settings = get_settings()
    try:
        from urllib.request import urlopen

        with urlopen(f"{settings.grobid_url.rstrip('/')}/api/isalive", timeout=2) as response:
            alive = response.read().decode("utf-8").strip().casefold()
    except Exception as error:  # noqa: BLE001 — skip when the service is down
        pytest.skip(f"GROBID unreachable at {settings.grobid_url}: {error}")

    if alive not in {"true", "1", "ok"}:
        pytest.skip(f"GROBID not alive at {settings.grobid_url}: {alive!r}")

    tei_xml = parse.process_fulltext_document(
        SAMPLE_GROBID_PDF,
        grobid_url=settings.grobid_url,
        headers={"User-Agent": "AI-Researcher/0.1 (mailto:researcher@example.com)"},
    )
    assert "<TEI" in tei_xml
    assert "<body" in tei_xml
