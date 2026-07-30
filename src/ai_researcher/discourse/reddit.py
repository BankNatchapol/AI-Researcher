"""Reddit community-attention discourse adapter (official OAuth API)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from time import monotonic, sleep
from urllib.parse import urlencode

from ai_researcher.config import get_settings
from ai_researcher.discourse.base import DiscourseItem
from ai_researcher.logging import get_logger
from ai_researcher.sources._http import (
    PostRequester,
    Requester,
    SourceHttp,
    request_bytes,
    request_post,
)
from ai_researcher.sources.base import PaperRef

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_OAUTH_BASE = "https://oauth.reddit.com"
_logger = get_logger(__name__)


class RedditSource:
    """Poll configured subreddits via Reddit's official OAuth API."""

    name = "reddit"

    def __init__(
        self,
        *,
        requester: Requester = request_bytes,
        post_requester: PostRequester = request_post,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._http = SourceHttp(
            self.name,
            requester=requester,
            post_requester=post_requester,
            clock=clock,
            sleeper=sleeper,
        )

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        settings = get_settings()
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            _logger.info(
                "Reddit adapter skipped: REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not configured"
            )
            return []

        token = self._access_token(
            settings.reddit_client_id,
            settings.reddit_client_secret,
        )
        auth_headers = {"Authorization": f"Bearer {token}"}
        since_utc = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        items: list[DiscourseItem] = []
        for subreddit in settings.reddit_subreddits:
            payload = self._http.get(
                f"{_OAUTH_BASE}/r/{subreddit}/new?{urlencode({'limit': 100})}",
                extra_headers=auth_headers,
            )
            items.extend(self._items_from_listing(payload, since_utc))
        return items

    def link_targets(self, item: DiscourseItem) -> list[PaperRef]:
        """Paper linking is shared logic landed in a later task."""

        del item
        return []

    def _access_token(self, client_id: str, client_secret: str) -> str:
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        payload = self._http.post(
            _TOKEN_URL,
            body=b"grant_type=client_credentials",
            content_type="application/x-www-form-urlencoded",
            extra_headers={"Authorization": f"Basic {basic}"},
        )
        data = json.loads(payload)
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Reddit OAuth response did not include access_token")
        return token

    @classmethod
    def _items_from_listing(cls, payload: bytes, since: datetime) -> list[DiscourseItem]:
        listing = json.loads(payload)
        children = listing.get("data", {}).get("children", [])
        items: list[DiscourseItem] = []
        for child in children:
            data = child.get("data") or {}
            created = data.get("created_utc")
            if created is None:
                continue
            posted_at = datetime.fromtimestamp(float(created), tz=UTC)
            if posted_at <= since:
                continue
            external_id = str(data.get("id") or "")
            permalink = data.get("permalink") or ""
            items.append(
                DiscourseItem(
                    source=cls.name,
                    external_id=external_id,
                    url=f"https://www.reddit.com{permalink}",
                    title=data.get("title"),
                    author=data.get("author"),
                    body=data.get("selftext") or data.get("url"),
                    posted_at=posted_at,
                    score=int(data["score"]) if data.get("score") is not None else None,
                    num_comments=(
                        int(data["num_comments"]) if data.get("num_comments") is not None else None
                    ),
                )
            )
        return items
