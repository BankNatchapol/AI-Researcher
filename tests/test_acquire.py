"""Offline tests for open-access PDF acquisition."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ai_researcher.sources import registry
from ai_researcher.sources.base import PaperRef

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FixtureSource:
    """Evidence source whose PDF URL is already present in the paper reference."""

    name: str = "arxiv"
    requested_refs: list[PaperRef] = field(default_factory=list)

    def search(self, scope, limit: int):
        raise AssertionError("acquisition must not search")

    def fetch_metadata(self, ref: PaperRef):
        raise AssertionError(f"acquisition must not fetch metadata for {ref.external_id}")

    def pdf_url(self, ref: PaperRef) -> str | None:
        self.requested_refs.append(ref)
        return ref.pdf_url


def _acquire_module():
    try:
        return importlib.import_module("ai_researcher.ingest.acquire")
    except ModuleNotFoundError:
        pytest.fail("ai_researcher.ingest.acquire has not been implemented")


@pytest.fixture(autouse=True)
def application_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("ARXIV_MIN_INTERVAL_SECONDS", "0")


def test_open_access_pdf_is_downloaded_and_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    assert hasattr(acquire, "AcquisitionPaper")
    assert hasattr(acquire, "PdfDownloadClient")
    assert hasattr(acquire, "acquire_pdf")

    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    paper_ref = PaperRef(
        source=source.name,
        external_id="unsafe/title",
        pdf_url="https://example.test/paper.pdf",
    )
    paper = acquire.AcquisitionPaper(id=42, ref=paper_ref)
    calls: list[tuple[str, dict[str, str]]] = []

    def request_fixture(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        return acquire.DownloadResponse(
            content=(FIXTURES / "sample.pdf").read_bytes(),
            content_type="application/pdf",
        )

    client = acquire.PdfDownloadClient(requester=request_fixture)

    result = acquire.acquire_pdf(
        paper,
        storage_dir=tmp_path,
        client=client,
    )

    expected_path = tmp_path / "42.pdf"
    assert result.status == "downloaded"
    assert result.paper_id == 42
    assert result.error is None
    assert paper.pdf_path == str(expected_path)
    assert paper.oa_status == "open_access"
    assert paper.parse_status == "pending"
    assert expected_path.read_bytes() == (FIXTURES / "sample.pdf").read_bytes()
    assert source.requested_refs == [paper_ref]
    assert calls == [
        (
            "https://example.test/paper.pdf",
            {
                "Accept": "application/pdf",
                "User-Agent": "AI-Researcher/0.1 (mailto:researcher@example.com)",
            },
        )
    ]


def test_paper_without_pdf_is_kept_as_abstract_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    paper_ref = PaperRef(source=source.name, external_id="abstract-only")
    paper = acquire.AcquisitionPaper(id=7, ref=paper_ref)

    def reject_request(url: str, headers: dict[str, str]):
        raise AssertionError(f"unexpected download: {url}, {headers}")

    result = acquire.acquire_pdf(
        paper,
        storage_dir=tmp_path,
        client=acquire.PdfDownloadClient(requester=reject_request),
    )

    assert result.status == "abstract_only"
    assert result.paper_id == 7
    assert result.error is None
    assert paper.pdf_path is None
    assert paper.oa_status == "not_available"
    assert paper.parse_status == "abstract_only"
    assert list(tmp_path.iterdir()) == []
    assert source.requested_refs == [paper_ref]


@pytest.mark.parametrize(
    ("content_type", "content"),
    [
        ("text/html", (FIXTURES / "sample.pdf").read_bytes()),
        ("application/pdf", b"<html>not a PDF</html>"),
    ],
)
def test_non_pdf_response_is_treated_as_no_pdf_available(
    content_type: str,
    content: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    paper = acquire.AcquisitionPaper(
        id=9,
        ref=PaperRef(
            source=source.name,
            external_id="not-a-pdf",
            pdf_url="https://example.test/not-a-pdf",
        ),
    )
    client = acquire.PdfDownloadClient(
        requester=lambda url, headers: acquire.DownloadResponse(
            content=content,
            content_type=content_type,
        )
    )

    result = acquire.acquire_pdf(paper, storage_dir=tmp_path, client=client)

    assert result.status == "abstract_only"
    assert result.error is None
    assert paper.pdf_path is None
    assert paper.oa_status == "not_available"
    assert paper.parse_status == "abstract_only"
    assert list(tmp_path.iterdir()) == []


def test_existing_download_is_skipped_without_touching_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    existing_path = tmp_path / "11.pdf"
    existing_path.write_bytes(b"existing bytes stay untouched")
    original_stat = existing_path.stat()
    paper = acquire.AcquisitionPaper(
        id=11,
        ref=PaperRef(
            source=source.name,
            external_id="already-downloaded",
            pdf_url="https://example.test/must-not-download.pdf",
        ),
        pdf_path=str(existing_path),
        oa_status="open_access",
    )

    def reject_request(url: str, headers: dict[str, str]):
        raise AssertionError(f"unexpected download: {url}, {headers}")

    result = acquire.acquire_pdf(
        paper,
        storage_dir=tmp_path,
        client=acquire.PdfDownloadClient(requester=reject_request),
    )

    assert result.status == "skipped"
    assert result.error is None
    assert existing_path.read_bytes() == b"existing bytes stay untouched"
    assert existing_path.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert paper.pdf_path == str(existing_path)
    assert paper.oa_status == "open_access"
    assert source.requested_refs == []


def test_download_failure_is_recorded_against_paper_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    paper = acquire.AcquisitionPaper(
        id=13,
        ref=PaperRef(
            source=source.name,
            external_id="network-failure",
            pdf_url="https://example.test/failure.pdf",
        ),
    )

    def fail_request(url: str, headers: dict[str, str]):
        raise OSError("connection reset by fixture")

    result = acquire.acquire_pdf(
        paper,
        storage_dir=tmp_path,
        client=acquire.PdfDownloadClient(requester=fail_request),
    )

    assert result.status == "failed"
    assert result.paper_id == 13
    assert result.error == "connection reset by fixture"
    assert paper.pdf_path is None
    assert paper.oa_status == "download_failed"
    assert paper.parse_status == "failed"
    assert list(tmp_path.iterdir()) == []


def test_default_acquisition_uses_configured_storage_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    paper = acquire.AcquisitionPaper(
        id=17,
        ref=PaperRef(
            source=source.name,
            external_id="configured-storage",
            pdf_url="https://example.test/configured.pdf",
        ),
    )
    client = acquire.PdfDownloadClient(
        requester=lambda url, headers: acquire.DownloadResponse(
            content=(FIXTURES / "sample.pdf").read_bytes(),
            content_type="application/pdf",
        )
    )

    result = acquire.acquire_pdf(paper, client=client)

    assert result.status == "downloaded"
    assert paper.pdf_path == str(tmp_path / "17.pdf")
    assert (tmp_path / "17.pdf").is_file()


def test_storage_failure_is_recorded_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = _acquire_module()
    source = FixtureSource()
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})
    blocked_storage = tmp_path / "not-a-directory"
    blocked_storage.write_text("file blocks directory creation")
    paper = acquire.AcquisitionPaper(
        id=19,
        ref=PaperRef(
            source=source.name,
            external_id="storage-failure",
            pdf_url="https://example.test/storage-failure.pdf",
        ),
    )
    client = acquire.PdfDownloadClient(
        requester=lambda url, headers: acquire.DownloadResponse(
            content=(FIXTURES / "sample.pdf").read_bytes(),
            content_type="application/pdf",
        )
    )

    result = acquire.acquire_pdf(
        paper,
        storage_dir=blocked_storage,
        client=client,
    )

    assert result.status == "failed"
    assert result.paper_id == 19
    assert result.error
    assert paper.pdf_path is None
    assert paper.oa_status == "download_failed"
    assert paper.parse_status == "failed"
