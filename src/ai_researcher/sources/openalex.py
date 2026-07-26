"""OpenAlex evidence-source adapter."""

import json
from collections.abc import Callable
from datetime import date
from time import monotonic, sleep
from urllib.parse import quote, urlencode

from ai_researcher.sources._http import Requester, SourceHttp, request_bytes
from ai_researcher.sources.base import PaperMetadata, PaperRef, Scope

_WORKS_URL = "https://api.openalex.org/works"


class OpenAlexSource:
    """Discover and normalize scholarly records from OpenAlex."""

    name = "openalex"

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
        filters = []
        if scope.date_from is not None:
            filters.append(f"from_publication_date:{scope.date_from.isoformat()}")
        if scope.date_to is not None:
            filters.append(f"to_publication_date:{scope.date_to.isoformat()}")
        parameters = {
            "search": " ".join(scope.include_terms),
            "per-page": limit,
        }
        if filters:
            parameters["filter"] = ",".join(filters)
        payload = self._json(self._http.get(f"{_WORKS_URL}?{urlencode(parameters)}"))
        return [self._ref(work) for work in payload.get("results", [])]

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata:
        work = self._json(self._http.get(f"{_WORKS_URL}/{quote(ref.external_id, safe='')}"))
        publication_date = work.get("publication_date")
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        return PaperMetadata(
            source=self.name,
            external_id=self._external_id(work.get("id", ref.external_id)),
            title=work.get("display_name") or "",
            abstract=self._abstract(work.get("abstract_inverted_index")),
            authors=tuple(
                authorship.get("author", {}).get("display_name")
                for authorship in work.get("authorships", [])
                if authorship.get("author", {}).get("display_name")
            ),
            published_at=date.fromisoformat(publication_date) if publication_date else None,
            venue=source.get("display_name"),
            doi=self._doi(work.get("doi")),
            openalex_id=self._external_id(work.get("id", ref.external_id)),
            pdf_url=self._oa_pdf_url(work),
        )

    def pdf_url(self, ref: PaperRef) -> str | None:
        return ref.pdf_url

    @staticmethod
    def _json(payload: bytes) -> dict:
        return json.loads(payload)

    @classmethod
    def _ref(cls, work: dict) -> PaperRef:
        return PaperRef(
            source=cls.name,
            external_id=cls._external_id(work["id"]),
            title=work.get("display_name"),
            doi=cls._doi(work.get("doi")),
            pdf_url=cls._oa_pdf_url(work),
        )

    @staticmethod
    def _external_id(identifier: str) -> str:
        return identifier.rstrip("/").rsplit("/", maxsplit=1)[-1]

    @staticmethod
    def _doi(doi: str | None) -> str | None:
        if doi is None:
            return None
        return doi.removeprefix("https://doi.org/")

    @staticmethod
    def _oa_pdf_url(work: dict) -> str | None:
        location = work.get("best_oa_location") or {}
        return location.get("pdf_url")

    @staticmethod
    def _abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
        if not inverted_index:
            return None
        positioned_words = [
            (position, word) for word, positions in inverted_index.items() for position in positions
        ]
        return " ".join(word for _, word in sorted(positioned_words))
