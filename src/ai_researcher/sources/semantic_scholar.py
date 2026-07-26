"""Semantic Scholar evidence-source adapter."""

import json
from collections.abc import Callable
from datetime import date
from time import monotonic, sleep
from urllib.parse import quote, urlencode

from ai_researcher.sources._http import Requester, SourceHttp, request_bytes
from ai_researcher.sources.base import PaperMetadata, PaperRef, Scope

_API_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = ",".join(
    (
        "paperId",
        "title",
        "abstract",
        "authors",
        "publicationDate",
        "venue",
        "externalIds",
        "openAccessPdf",
    )
)


class SemanticScholarSource:
    """Discover and normalize scholarly records from Semantic Scholar."""

    name = "semantic_scholar"

    def __init__(
        self,
        *,
        requester: Requester = request_bytes,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._http = SourceHttp(
            self.name,
            requester=requester,
            clock=clock,
            sleeper=sleeper,
        )

    @property
    def requester(self) -> Requester:
        return self._http.requester

    @requester.setter
    def requester(self, requester: Requester) -> None:
        self._http.requester = requester

    def search(self, scope: Scope, limit: int) -> list[PaperRef]:
        parameters = {
            "query": " ".join(scope.include_terms),
            "limit": limit,
            "fields": _FIELDS,
        }
        if scope.date_from is not None or scope.date_to is not None:
            start = scope.date_from.isoformat() if scope.date_from else ""
            end = scope.date_to.isoformat() if scope.date_to else ""
            parameters["publicationDateOrYear"] = f"{start}:{end}"
        url = f"{_API_URL}/paper/search?{urlencode(parameters)}"
        payload = self._json(self._http.get(url))
        return [self._ref(paper) for paper in payload.get("data", [])]

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata:
        url = f"{_API_URL}/paper/{quote(ref.external_id, safe='')}?{urlencode({'fields': _FIELDS})}"
        paper = self._json(self._http.get(url))
        publication_date = paper.get("publicationDate")
        external_ids = paper.get("externalIds") or {}
        return PaperMetadata(
            source=self.name,
            external_id=paper.get("paperId", ref.external_id),
            title=paper.get("title") or "",
            abstract=paper.get("abstract"),
            authors=tuple(
                author["name"] for author in paper.get("authors", []) if author.get("name")
            ),
            published_at=date.fromisoformat(publication_date) if publication_date else None,
            venue=paper.get("venue"),
            doi=external_ids.get("DOI"),
            arxiv_id=external_ids.get("ArXiv"),
            s2_id=paper.get("paperId", ref.external_id),
            pdf_url=self._pdf_url(paper),
        )

    def pdf_url(self, ref: PaperRef) -> str | None:
        return ref.pdf_url

    @staticmethod
    def _json(payload: bytes) -> dict:
        return json.loads(payload)

    @classmethod
    def _ref(cls, paper: dict) -> PaperRef:
        external_ids = paper.get("externalIds") or {}
        return PaperRef(
            source=cls.name,
            external_id=paper["paperId"],
            title=paper.get("title"),
            doi=external_ids.get("DOI"),
            pdf_url=cls._pdf_url(paper),
        )

    @staticmethod
    def _pdf_url(paper: dict) -> str | None:
        open_access_pdf = paper.get("openAccessPdf") or {}
        return open_access_pdf.get("url")
