"""arXiv evidence-source adapter."""

from collections.abc import Callable
from datetime import date
from time import monotonic, sleep
from urllib.parse import urlencode
from xml.etree import ElementTree

from ai_researcher.sources._http import Requester, SourceHttp, request_bytes
from ai_researcher.sources.base import PaperMetadata, PaperRef, Scope

_API_URL = "https://export.arxiv.org/api/query"
_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV = "http://arxiv.org/schemas/atom"


class ArxivSource:
    """Discover and normalize scholarly records from arXiv."""

    name = "arxiv"

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
        query_parts = [f'all:"{term}"' for term in scope.include_terms]
        query_parts.extend(f"cat:{category}" for category in scope.categories)
        if scope.date_from is not None or scope.date_to is not None:
            date_from = scope.date_from or date.min
            date_to = scope.date_to or date.max
            query_parts.append(f"submittedDate:[{date_from:%Y%m%d}0000 TO {date_to:%Y%m%d}2359]")
        search_query = " AND ".join(query_parts)
        search_query += "".join(f' ANDNOT all:"{term}"' for term in scope.exclude_terms)
        parameters = {
            "search_query": search_query,
            "start": 0,
            "max_results": limit,
        }
        url = f"{_API_URL}?{urlencode(parameters)}"
        return self._parse_refs(self._http.get(url, accept="application/atom+xml"))

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata:
        url = f"{_API_URL}?{urlencode({'id_list': ref.external_id, 'max_results': 1})}"
        entries = self._entries(self._http.get(url, accept="application/atom+xml"))
        if not entries:
            raise LookupError(f"arXiv paper not found: {ref.external_id}")
        return self._metadata(entries[0])

    def pdf_url(self, ref: PaperRef) -> str | None:
        return ref.pdf_url or f"https://arxiv.org/pdf/{ref.external_id}"

    @staticmethod
    def _entries(payload: bytes) -> list[ElementTree.Element]:
        root = ElementTree.fromstring(payload)
        return list(root.findall(f"{{{_ATOM}}}entry"))

    @classmethod
    def _parse_refs(cls, payload: bytes) -> list[PaperRef]:
        refs = []
        for entry in cls._entries(payload):
            external_id = cls._external_id(entry)
            refs.append(
                PaperRef(
                    source=cls.name,
                    external_id=external_id,
                    title=cls._text(entry, "title"),
                    doi=cls._text(entry, "doi", namespace=_ARXIV),
                    pdf_url=cls._pdf_link(entry),
                )
            )
        return refs

    @classmethod
    def _metadata(cls, entry: ElementTree.Element) -> PaperMetadata:
        external_id = cls._external_id(entry)
        published = cls._text(entry, "published")
        return PaperMetadata(
            source=cls.name,
            external_id=external_id,
            title=cls._text(entry, "title") or "",
            abstract=cls._text(entry, "summary"),
            authors=tuple(
                name.text.strip()
                for name in entry.findall(f"{{{_ATOM}}}author/{{{_ATOM}}}name")
                if name.text
            ),
            published_at=date.fromisoformat(published[:10]) if published else None,
            venue=cls._text(entry, "journal_ref", namespace=_ARXIV),
            doi=cls._text(entry, "doi", namespace=_ARXIV),
            arxiv_id=external_id,
            is_preprint=True,
            pdf_url=cls._pdf_link(entry),
        )

    @staticmethod
    def _text(
        entry: ElementTree.Element,
        name: str,
        *,
        namespace: str = _ATOM,
    ) -> str | None:
        element = entry.find(f"{{{namespace}}}{name}")
        if element is None or element.text is None:
            return None
        return " ".join(element.text.split())

    @classmethod
    def _external_id(cls, entry: ElementTree.Element) -> str:
        identifier = cls._text(entry, "id") or ""
        return identifier.rstrip("/").rsplit("/", maxsplit=1)[-1]

    @staticmethod
    def _pdf_link(entry: ElementTree.Element) -> str | None:
        for link in entry.findall(f"{{{_ATOM}}}link"):
            if link.attrib.get("title") == "pdf":
                return link.attrib.get("href")
        return None
