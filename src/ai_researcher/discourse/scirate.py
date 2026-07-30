"""SciRate community-attention spike adapter (signal-only; disabled by default).

SciRate \"scites\" are community upvotes — an attention signal, not validity.
This adapter belongs strictly to the discourse channel and must never feed
``scoring/``. Compliant live fetches currently fail behind Cloudflare 403;
see ``docs/supersaiyan/designs/scirate-spike.md``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from time import monotonic, sleep
from urllib.error import HTTPError, URLError

from ai_researcher.config import get_settings
from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin
from ai_researcher.logging import get_logger
from ai_researcher.sources._http import Requester, SourceHttp, request_bytes

_SCIRATE_PAPER_URL = "https://scirate.com/arxiv/{arxiv_id}"
# Numeric scite count only — never capture surrounding page prose.
_SCITE_COUNT = re.compile(r"(?i)(\d+)\s*scites?\b")

_logger = get_logger(__name__)


class SciRateSource(DiscourseLinkMixin):
    """Fetch scite counts keyed by arXiv ID; no-op unless explicitly enabled."""

    name = "scirate"

    def __init__(
        self,
        *,
        requester: Requester = request_bytes,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        arxiv_ids: Sequence[str] | None = None,
    ) -> None:
        self._http = SourceHttp(
            self.name,
            requester=requester,
            clock=clock,
            sleeper=sleeper,
        )
        self._arxiv_ids = tuple(arxiv_ids) if arxiv_ids is not None else None

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        del since  # scite counts are current snapshots, not a chronological feed
        settings = get_settings()
        if not settings.discourse_scirate_enabled:
            _logger.info("SciRate adapter disabled; set DISCOURSE_SCIRATE_ENABLED=true to activate")
            return []

        arxiv_ids = self._arxiv_ids
        if arxiv_ids is None:
            arxiv_ids = settings.discourse_scirate_arxiv_ids
        if not arxiv_ids:
            _logger.info("SciRate adapter enabled but no arXiv IDs configured; skipping")
            return []

        items: list[DiscourseItem] = []
        for arxiv_id in arxiv_ids:
            item = self._fetch_signal(arxiv_id)
            if item is not None:
                items.append(item)
        return items

    def _fetch_signal(self, arxiv_id: str) -> DiscourseItem | None:
        url = _SCIRATE_PAPER_URL.format(arxiv_id=arxiv_id)
        try:
            payload = self._http.get(url, accept="text/html")
        except HTTPError as error:
            if error.code == 403:
                _logger.info(
                    "SciRate returned 403 for %s; degrading silently (no page content stored)",
                    arxiv_id,
                )
                return None
            _logger.info(
                "SciRate HTTP %s for %s; degrading silently",
                error.code,
                arxiv_id,
            )
            return None
        except (URLError, TimeoutError, OSError) as error:
            _logger.info(
                "SciRate fetch failed for %s (%s); degrading silently",
                arxiv_id,
                error,
            )
            return None

        count = _parse_scite_count(payload)
        if count is None:
            _logger.info("SciRate page for %s had no parseable scite count", arxiv_id)
            return None

        # Signal only: arXiv ID, link back, scite count — never page body/title.
        return DiscourseItem(
            source=self.name,
            external_id=arxiv_id,
            url=url,
            title=None,
            author=None,
            body=None,
            posted_at=None,
            score=count,
            num_comments=None,
        )


def _parse_scite_count(payload: bytes) -> int | None:
    """Extract the numeric scite count; discard all other HTML content."""

    # Decode only enough to regex-match the count token; never return page text.
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 — treat decode failure as no signal
        return None
    match = _SCITE_COUNT.search(text)
    if match is None:
        return None
    return int(match.group(1))
