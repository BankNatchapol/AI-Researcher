"""Shared HTTP mechanics for independently implemented source adapters."""

from collections.abc import Callable
from time import monotonic, sleep
from urllib.request import Request, urlopen

from ai_researcher.config import get_settings
from ai_researcher.sources.ratelimit import MinimumIntervalLimiter

Requester = Callable[[str, dict[str, str]], bytes]


def request_bytes(url: str, headers: dict[str, str]) -> bytes:
    """Fetch bytes using the standard library's non-persistent HTTP client."""

    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read()


class SourceHttp:
    """Apply source configuration consistently around an injectable requester."""

    def __init__(
        self,
        source_name: str,
        *,
        requester: Requester = request_bytes,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.source_name = source_name
        self.requester = requester
        self._clock = clock
        self._sleeper = sleeper
        self._limiter: MinimumIntervalLimiter | None = None
        self._configured_interval: float | None = None

    def get(self, url: str, *, accept: str = "application/json") -> bytes:
        """Rate-limit and execute one configured GET request."""

        settings = get_settings()
        interval = settings.source_min_intervals[self.source_name]
        if self._limiter is None or interval != self._configured_interval:
            self._limiter = MinimumIntervalLimiter(
                interval,
                clock=self._clock,
                sleeper=self._sleeper,
            )
            self._configured_interval = interval
        self._limiter.wait()
        headers = {
            "Accept": accept,
            "User-Agent": f"AI-Researcher/0.1 (mailto:{settings.contact_email})",
        }
        return self.requester(url, headers)
