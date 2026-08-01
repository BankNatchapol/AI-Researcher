"""Shared HTTP mechanics for independently implemented source adapters."""

from collections.abc import Callable
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_researcher.config import get_settings
from ai_researcher.logging import get_logger
from ai_researcher.sources.ratelimit import MinimumIntervalLimiter

Requester = Callable[[str, dict[str, str]], bytes]
PostRequester = Callable[[str, dict[str, str], bytes], bytes]

logger = get_logger(__name__)

_DEFAULT_MAX_ATTEMPTS = 4
_DEFAULT_INITIAL_BACKOFF_SECONDS = 2.0
_DEFAULT_BACKOFF_MULTIPLIER = 2.0
_MAX_BACKOFF_SECONDS = 30.0
_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def request_bytes(url: str, headers: dict[str, str]) -> bytes:
    """Fetch bytes using the standard library's non-persistent HTTP client."""

    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read()


def request_post(url: str, headers: dict[str, str], body: bytes) -> bytes:
    """POST bytes using the standard library's non-persistent HTTP client."""

    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=30) as response:
        return response.read()


def _retry_after_seconds(error: HTTPError) -> float | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None  # HTTP-date form unsupported; fall back to exponential backoff


class SourceHttp:
    """Apply source configuration consistently around an injectable requester."""

    def __init__(
        self,
        source_name: str,
        *,
        requester: Requester = request_bytes,
        post_requester: PostRequester = request_post,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        initial_backoff_seconds: float = _DEFAULT_INITIAL_BACKOFF_SECONDS,
        backoff_multiplier: float = _DEFAULT_BACKOFF_MULTIPLIER,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.source_name = source_name
        self.requester = requester
        self.post_requester = post_requester
        self._clock = clock
        self._sleeper = sleeper
        self._limiter: MinimumIntervalLimiter | None = None
        self._configured_interval: float | None = None
        self._max_attempts = max_attempts
        self._initial_backoff_seconds = initial_backoff_seconds
        self._backoff_multiplier = backoff_multiplier

    def _wait(self) -> None:
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

    def _user_agent(self) -> str:
        return f"AI-Researcher/0.1 (mailto:{get_settings().contact_email})"

    def _send_with_retry(self, action: Callable[[], bytes]) -> bytes:
        backoff = self._initial_backoff_seconds
        for attempt in range(1, self._max_attempts + 1):
            self._wait()
            try:
                return action()
            except HTTPError as error:
                retryable = error.code in _RETRYABLE_STATUS_CODES
                delay = _retry_after_seconds(error)
                caught: Exception = error
            except (URLError, TimeoutError, OSError) as error:
                retryable = True
                delay = None
                caught = error

            if not retryable or attempt >= self._max_attempts:
                raise caught

            wait_seconds = min(backoff if delay is None else delay, _MAX_BACKOFF_SECONDS)
            logger.warning(
                "%s request failed (%s) on attempt %d/%d; retrying in %.1fs",
                self.source_name,
                caught,
                attempt,
                self._max_attempts,
                wait_seconds,
            )
            self._sleeper(wait_seconds)
            backoff = min(backoff * self._backoff_multiplier, _MAX_BACKOFF_SECONDS)
        raise AssertionError("unreachable: loop always returns or raises")

    def get(
        self,
        url: str,
        *,
        accept: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        """Rate-limit and execute one configured GET request, retrying transient failures."""

        headers = {
            "Accept": accept,
            "User-Agent": self._user_agent(),
        }
        if extra_headers:
            headers.update(extra_headers)
        return self._send_with_retry(lambda: self.requester(url, headers))

    def post(
        self,
        url: str,
        *,
        body: bytes,
        content_type: str,
        accept: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        """Rate-limit and execute one configured POST request, retrying transient failures."""

        headers = {
            "Accept": accept,
            "Content-Type": content_type,
            "User-Agent": self._user_agent(),
        }
        if extra_headers:
            headers.update(extra_headers)
        return self._send_with_retry(lambda: self.post_requester(url, headers, body))
