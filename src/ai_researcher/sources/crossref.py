"""Crossref DOI resolution helper."""

import json
from urllib.parse import urlencode

from ai_researcher.sources._http import Requester, SourceHttp, request_bytes

_WORKS_URL = "https://api.crossref.org/works"


def resolve_doi(
    title: str,
    *,
    requester: Requester = request_bytes,
) -> str | None:
    """Resolve a title to a DOI without acting as a discovery adapter."""

    http = SourceHttp("crossref", requester=requester)
    url = f"{_WORKS_URL}?{urlencode({'query.title': title, 'rows': 1})}"
    payload = json.loads(http.get(url))
    items = payload.get("message", {}).get("items", [])
    return items[0].get("DOI") if items else None
