"""Open-access PDF acquisition without persistence side effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from urllib.request import Request, urlopen

from ai_researcher.config import get_settings
from ai_researcher.sources import registry
from ai_researcher.sources.base import PaperRef
from ai_researcher.sources.ratelimit import MinimumIntervalLimiter


@dataclass(slots=True)
class AcquisitionPaper:
    """Mutable acquisition fields corresponding to one persisted paper row."""

    id: int
    ref: PaperRef
    pdf_path: str | None = None
    oa_status: str | None = None
    parse_status: str = "pending"


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """Outcome linked to the paper whose acquisition was attempted."""

    paper_id: int
    status: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadResponse:
    """HTTP response fields required to validate a PDF download."""

    content: bytes
    content_type: str | None


DownloadRequester = Callable[[str, dict[str, str]], DownloadResponse]


def request_download(url: str, headers: dict[str, str]) -> DownloadResponse:
    """Fetch a candidate PDF with the standard library HTTP client."""

    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return DownloadResponse(
            content=response.read(),
            content_type=response.headers.get_content_type(),
        )


class PdfDownloadClient:
    """Apply adapter-equivalent headers and per-source rate limiting to downloads."""

    def __init__(
        self,
        *,
        requester: DownloadRequester = request_download,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._requester = requester
        self._clock = clock
        self._sleeper = sleeper
        self._limiters: dict[str, tuple[float, MinimumIntervalLimiter]] = {}

    def get(self, source_name: str, url: str) -> DownloadResponse:
        """Rate-limit and download one source-owned PDF URL."""

        settings = get_settings()
        interval = settings.source_min_intervals[source_name]
        configured = self._limiters.get(source_name)
        if configured is None or configured[0] != interval:
            configured = (
                interval,
                MinimumIntervalLimiter(
                    interval,
                    clock=self._clock,
                    sleeper=self._sleeper,
                ),
            )
            self._limiters[source_name] = configured
        configured[1].wait()
        return self._requester(
            url,
            {
                "Accept": "application/pdf",
                "User-Agent": f"AI-Researcher/0.1 (mailto:{settings.contact_email})",
            },
        )


_DEFAULT_CLIENT = PdfDownloadClient()


def acquire_pdf(
    paper: AcquisitionPaper,
    *,
    storage_dir: str | Path | None = None,
    client: PdfDownloadClient = _DEFAULT_CLIENT,
) -> AcquisitionResult:
    """Download and record an openly accessible PDF for one paper."""

    if paper.pdf_path is not None and Path(paper.pdf_path).is_file():
        return AcquisitionResult(paper_id=paper.id, status="skipped")

    source = registry.get(paper.ref.source)
    pdf_url = source.pdf_url(paper.ref)
    if pdf_url is None:
        paper.oa_status = "not_available"
        paper.parse_status = "abstract_only"
        return AcquisitionResult(paper_id=paper.id, status="abstract_only")

    try:
        response = client.get(source.name, pdf_url)
    except OSError as error:
        return _record_failure(paper, error)
    content_type = (response.content_type or "").partition(";")[0].strip().casefold()
    if content_type != "application/pdf" or not response.content.startswith(b"%PDF-"):
        paper.oa_status = "not_available"
        paper.parse_status = "abstract_only"
        return AcquisitionResult(paper_id=paper.id, status="abstract_only")

    directory = Path(storage_dir) if storage_dir is not None else get_settings().storage_dir
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{paper.id}.pdf"
        destination.write_bytes(response.content)
    except OSError as error:
        return _record_failure(paper, error)

    paper.pdf_path = str(destination)
    paper.oa_status = "open_access"
    return AcquisitionResult(paper_id=paper.id, status="downloaded")


def _record_failure(
    paper: AcquisitionPaper,
    error: OSError,
) -> AcquisitionResult:
    paper.oa_status = "download_failed"
    paper.parse_status = "failed"
    return AcquisitionResult(
        paper_id=paper.id,
        status="failed",
        error=str(error),
    )


__all__ = [
    "AcquisitionPaper",
    "AcquisitionResult",
    "DownloadResponse",
    "PdfDownloadClient",
    "acquire_pdf",
]
