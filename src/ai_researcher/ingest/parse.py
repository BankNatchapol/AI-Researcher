"""GROBID PDF parsing into TEI XML and normalized section records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_researcher.config import get_settings
from ai_researcher.ingest.tei import SectionRecord, tei_to_sections

GrobidProcessor = Callable[..., str]


@dataclass(slots=True)
class ParsePaper:
    """Mutable parse fields corresponding to one persisted paper row."""

    id: int
    pdf_path: str | None = None
    tei_xml: str | None = None
    parse_status: str = "pending"


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Outcome linked to the paper whose parse was attempted."""

    paper_id: int
    status: str
    sections: list[SectionRecord] = field(default_factory=list)
    error: str | None = None


def process_fulltext_document(
    pdf_file: Path,
    *,
    grobid_url: str,
    headers: dict[str, str],
) -> str:
    """POST a PDF to GROBID ``/api/processFulltextDocument`` and return TEI XML."""

    endpoint = f"{grobid_url.rstrip('/')}/api/processFulltextDocument"
    boundary = "----AIResearcherGrobidBoundary"
    pdf_bytes = pdf_file.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                b'Content-Disposition: form-data; name="input"; '
                + f'filename="{pdf_file.name}"\r\n'.encode()
                + b"Content-Type: application/pdf\r\n\r\n"
            ),
            pdf_bytes,
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="teiCoordinates"\r\n\r\n',
            b"p,head,figure,ref,biblStruct,formula,s\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = Request(
        endpoint,
        data=body,
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/xml",
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def parse_pdf(
    paper: ParsePaper,
    *,
    processor: GrobidProcessor | None = None,
) -> ParseResult:
    """Parse one paper's PDF through GROBID into TEI and section records."""

    if not paper.pdf_path:
        return _record_failure(paper, "paper.pdf_path is missing")

    pdf_path = Path(paper.pdf_path)
    if not pdf_path.is_file():
        return _record_failure(paper, f"PDF not found: {pdf_path}")

    settings = get_settings()
    headers = {"User-Agent": f"AI-Researcher/0.1 (mailto:{settings.contact_email})"}
    run = processor or process_fulltext_document

    try:
        tei_xml = run(pdf_path, grobid_url=settings.grobid_url, headers=headers)
    except (OSError, URLError, HTTPError, HTTPException, TimeoutError, ValueError) as error:
        return _record_failure(paper, error)

    sections = tei_to_sections(tei_xml)
    paper.tei_xml = tei_xml
    paper.parse_status = "parsed"
    return ParseResult(paper_id=paper.id, status="parsed", sections=sections)


def _record_failure(paper: ParsePaper, error: object) -> ParseResult:
    paper.parse_status = "failed"
    paper.tei_xml = None
    return ParseResult(
        paper_id=paper.id,
        status="failed",
        sections=[],
        error=str(error),
    )


__all__ = [
    "ParsePaper",
    "ParseResult",
    "parse_pdf",
    "process_fulltext_document",
]
