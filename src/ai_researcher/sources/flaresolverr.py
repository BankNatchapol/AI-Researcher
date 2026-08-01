"""Client for a locally run FlareSolverr Cloudflare-challenge-solving proxy.

FlareSolverr (https://github.com/FlareSolverr/FlareSolverr) is a standalone Docker
service, not a Python library — it runs its own headless browser and exposes a JSON
command API over HTTP. This client POSTs one ``request.get`` command to that API and
returns the resolved HTML, or raises a typed error.

This is reusable infrastructure for a future scraped source; nothing in this codebase
calls it yet, and it deliberately does not implement ``EvidenceSource`` or
``DiscourseSource`` — it must never be registered as a source itself.

Session reuse (FlareSolverr's ``sessions.create``/``sessions.destroy``, which avoids
re-solving a challenge on every call) is deliberately not implemented — there is no real
target site yet to say whether cookie continuity across calls even matters for it.
"""

import json
from collections.abc import Callable
from time import monotonic, sleep
from urllib.error import HTTPError, URLError

from ai_researcher.config import get_settings
from ai_researcher.sources._http import PostRequester, request_post
from ai_researcher.sources.ratelimit import MinimumIntervalLimiter

_DEFAULT_MAX_TIMEOUT_MS = 60_000
_DEFAULT_MIN_INTERVAL_SECONDS = 1.0


class FlareSolverrError(RuntimeError):
    """Base class for FlareSolverrClient failures."""


class FlareSolverrNotConfiguredError(FlareSolverrError):
    """No flaresolverr_url was passed and FLARESOLVERR_URL is unset."""


class FlareSolverrRequestError(FlareSolverrError):
    """FlareSolverr itself failed: unreachable, bad JSON, or status == "error"."""


class FlareSolverrResponseError(FlareSolverrError):
    """FlareSolverr solved the challenge but the target page itself was non-2xx."""

    def __init__(self, url: str, status_code: int) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(f"FlareSolverr resolved {url} with status {status_code}")


class FlareSolverrClient:
    """Fetch a URL's resolved HTML through a locally run FlareSolverr instance."""

    def __init__(
        self,
        *,
        flaresolverr_url: str | None = None,
        post_requester: PostRequester = request_post,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        min_interval_seconds: float = _DEFAULT_MIN_INTERVAL_SECONDS,
        max_timeout_ms: int = _DEFAULT_MAX_TIMEOUT_MS,
    ) -> None:
        self._explicit_url = flaresolverr_url
        self._post_requester = post_requester
        self._limiter = MinimumIntervalLimiter(min_interval_seconds, clock=clock, sleeper=sleeper)
        self._max_timeout_ms = max_timeout_ms

    def fetch(self, url: str) -> str:
        """Resolve ``url`` through FlareSolverr and return its rendered HTML."""

        target_url = self._explicit_url or get_settings().flaresolverr_url
        if not target_url:
            raise FlareSolverrNotConfiguredError(
                "FlareSolverrClient requires flaresolverr_url or FLARESOLVERR_URL"
            )
        body = json.dumps(
            {"cmd": "request.get", "url": url, "maxTimeout": self._max_timeout_ms}
        ).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        self._limiter.wait()
        try:
            raw = self._post_requester(target_url, headers, body)
        except HTTPError as error:
            raise FlareSolverrRequestError(
                f"FlareSolverr HTTP {error.code}: {error.reason}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise FlareSolverrRequestError(
                f"Could not reach FlareSolverr at {target_url}: {error}"
            ) from error

        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise FlareSolverrRequestError(
                f"FlareSolverr returned invalid JSON: {error}"
            ) from error

        if payload.get("status") != "ok":
            raise FlareSolverrRequestError(
                f"FlareSolverr failed to resolve {url}: {payload.get('message', 'unknown error')}"
            )

        solution = payload.get("solution") or {}
        response_status = solution.get("status")
        if response_status is not None and not (200 <= response_status < 300):
            raise FlareSolverrResponseError(url, response_status)

        html = solution.get("response")
        if html is None:
            raise FlareSolverrRequestError(
                f"FlareSolverr response for {url} had no solution.response"
            )
        return html


__all__ = [
    "FlareSolverrClient",
    "FlareSolverrError",
    "FlareSolverrNotConfiguredError",
    "FlareSolverrRequestError",
    "FlareSolverrResponseError",
]
