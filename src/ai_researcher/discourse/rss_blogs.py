"""Config-driven RSS / Atom discourse adapter for research blogs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic, sleep
from xml.etree import ElementTree

from ai_researcher.config import get_settings
from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin
from ai_researcher.logging import get_logger
from ai_researcher.sources._http import Requester, SourceHttp, request_bytes

_ATOM = "http://www.w3.org/2005/Atom"
_logger = get_logger(__name__)


class RssBlogsSource(DiscourseLinkMixin):
    """Poll every feed URL in ``DISCOURSE_RSS_FEEDS`` (RSS and Atom).

    Each configured URL is fetched independently. A malformed or unreachable
    feed is logged and skipped so the remaining feeds still poll.
    """

    name = "rss_blogs"

    def __init__(
        self,
        *,
        feed_urls: tuple[str, ...] | None = None,
        requester: Requester = request_bytes,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._feed_urls = feed_urls
        self._http = SourceHttp(
            "rss",
            requester=requester,
            clock=clock,
            sleeper=sleeper,
        )

    def _urls(self) -> tuple[str, ...]:
        if self._feed_urls is not None:
            return self._feed_urls
        return get_settings().discourse_rss_feeds

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        since_utc = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        items: list[DiscourseItem] = []
        for url in self._urls():
            try:
                payload = self._http.get(
                    url,
                    accept=(
                        "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"
                    ),
                )
                items.extend(self._items_from_payload(payload, since_utc))
            except Exception as error:  # noqa: BLE001 — skip bad feeds, continue others
                _logger.warning(
                    "RSS feed skipped (malformed or unreachable): %s (%s)",
                    url,
                    error,
                )
        return items

    @classmethod
    def _items_from_payload(cls, payload: bytes, since: datetime) -> list[DiscourseItem]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as error:
            raise ValueError(f"malformed feed XML: {error}") from error

        tag = _local(root.tag).lower()
        if tag == "rss":
            return cls._items_from_rss(root, since)
        if tag == "feed":
            return cls._items_from_atom(root, since)
        raise ValueError(f"unsupported feed root element: {tag}")

    @classmethod
    def _items_from_rss(cls, root: ElementTree.Element, since: datetime) -> list[DiscourseItem]:
        items: list[DiscourseItem] = []
        channel = root.find("channel")
        if channel is None:
            return items
        for entry in channel.findall("item"):
            posted_at = _parse_rss_date(_child_text(entry, "pubDate"))
            if posted_at is None or posted_at <= since:
                continue
            link = _child_text(entry, "link") or ""
            guid = _child_text(entry, "guid") or link
            items.append(
                DiscourseItem(
                    source=cls.name,
                    external_id=guid,
                    url=link or guid,
                    title=_child_text(entry, "title"),
                    author=_child_text(entry, "author") or _child_text(entry, "dc:creator"),
                    body=_child_text(entry, "description"),
                    posted_at=posted_at,
                )
            )
        return items

    @classmethod
    def _items_from_atom(cls, root: ElementTree.Element, since: datetime) -> list[DiscourseItem]:
        items: list[DiscourseItem] = []
        for entry in root.findall(f"{{{_ATOM}}}entry"):
            published = _atom_text(entry, "published") or _atom_text(entry, "updated")
            posted_at = _parse_iso_datetime(published)
            if posted_at is None or posted_at <= since:
                continue
            entry_id = _atom_text(entry, "id") or ""
            link = _atom_link(entry) or entry_id
            author_el = entry.find(f"{{{_ATOM}}}author/{{{_ATOM}}}name")
            author = author_el.text.strip() if author_el is not None and author_el.text else None
            items.append(
                DiscourseItem(
                    source=cls.name,
                    external_id=entry_id,
                    url=link,
                    title=_atom_text(entry, "title"),
                    author=author,
                    body=_atom_text(entry, "summary") or _atom_text(entry, "content"),
                    posted_at=posted_at,
                )
            )
        return items


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(parent: ElementTree.Element, name: str) -> str | None:
    child = parent.find(name)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _atom_text(entry: ElementTree.Element, name: str) -> str | None:
    child = entry.find(f"{{{_ATOM}}}{name}")
    if child is None or child.text is None:
        return None
    text = " ".join(child.text.split())
    return text or None


def _atom_link(entry: ElementTree.Element) -> str | None:
    alternate = None
    for link in entry.findall(f"{{{_ATOM}}}link"):
        href = link.attrib.get("href")
        if not href:
            continue
        rel = link.attrib.get("rel", "alternate")
        if rel == "alternate":
            return href
        if alternate is None:
            alternate = href
    return alternate


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


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return _parse_iso_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
