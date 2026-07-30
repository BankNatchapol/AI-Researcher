"""Hacker News community-attention discourse adapter (public Firebase API)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from time import monotonic, sleep

from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin
from ai_researcher.sources._http import Requester, SourceHttp, request_bytes

_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_MAX_ITEMS_PER_POLL = 50


class HackerNewsSource(DiscourseLinkMixin):
    """Poll recent HN stories via the public Firebase API; no credentials."""

    name = "hackernews"

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
        story_ids = json.loads(self._http.get(f"{_FIREBASE_BASE}/newstories.json"))
        items: list[DiscourseItem] = []
        for story_id in story_ids[:_MAX_ITEMS_PER_POLL]:
            payload = self._http.get(f"{_FIREBASE_BASE}/item/{story_id}.json")
            item = self._item_from_payload(payload, since_utc)
            if item is None:
                continue
            items.append(item)
        return items

    @classmethod
    def _item_from_payload(cls, payload: bytes, since: datetime) -> DiscourseItem | None:
        data = json.loads(payload)
        if not data or data.get("type") != "story":
            return None
        created = data.get("time")
        if created is None:
            return None
        posted_at = datetime.fromtimestamp(int(created), tz=UTC)
        if posted_at <= since:
            return None
        external_id = str(data["id"])
        story_url = data.get("url")
        text = data.get("text")
        body_parts = [part for part in (story_url, text) if part]
        return DiscourseItem(
            source=cls.name,
            external_id=external_id,
            url=f"https://news.ycombinator.com/item?id={external_id}",
            title=data.get("title"),
            author=data.get("by"),
            body="\n".join(body_parts) if body_parts else None,
            posted_at=posted_at,
            score=int(data["score"]) if data.get("score") is not None else None,
            num_comments=(
                int(data["descendants"]) if data.get("descendants") is not None else None
            ),
        )
