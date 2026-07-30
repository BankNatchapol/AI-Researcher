"""Hugging Face Papers / alphaXiv daily curated-attention discourse adapter."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from time import monotonic, sleep

from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin
from ai_researcher.sources._http import Requester, SourceHttp, request_bytes

_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"


class HuggingFacePapersSource(DiscourseLinkMixin):
    """Poll Hugging Face daily papers (arXiv IDs with upvote attention counts)."""

    name = "huggingface"

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

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        since_utc = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        payload = self._http.get(_DAILY_PAPERS_URL)
        return self._items_from_payload(payload, since_utc)

    @classmethod
    def _items_from_payload(cls, payload: bytes, since: datetime) -> list[DiscourseItem]:
        listing = json.loads(payload)
        if not isinstance(listing, list):
            return []
        items: list[DiscourseItem] = []
        for entry in listing:
            if not isinstance(entry, dict):
                continue
            paper = entry.get("paper") or {}
            if not isinstance(paper, dict):
                continue
            paper_id = str(paper.get("id") or "").strip()
            if not paper_id:
                continue
            posted_raw = (
                paper.get("submittedOnDailyAt")
                or entry.get("publishedAt")
                or paper.get("publishedAt")
            )
            posted_at = _parse_iso_datetime(posted_raw if isinstance(posted_raw, str) else None)
            if posted_at is None or posted_at <= since:
                continue
            submitter = entry.get("submittedBy") or paper.get("submittedOnDailyBy") or {}
            author = None
            if isinstance(submitter, dict):
                author = submitter.get("fullname") or submitter.get("name")
            upvotes = paper.get("upvotes")
            comments = entry.get("numComments")
            items.append(
                DiscourseItem(
                    source=cls.name,
                    external_id=paper_id,
                    url=f"https://huggingface.co/papers/{paper_id}",
                    title=paper.get("title") or entry.get("title"),
                    author=author if isinstance(author, str) else None,
                    body=paper.get("summary") or entry.get("summary"),
                    posted_at=posted_at,
                    score=int(upvotes) if upvotes is not None else None,
                    num_comments=int(comments) if comments is not None else None,
                )
            )
        return items


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
