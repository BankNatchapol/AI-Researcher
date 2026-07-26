"""Thread-safe minimum-interval rate limiting for source adapters."""

from collections.abc import Callable
from threading import Lock
from time import monotonic, sleep


class MinimumIntervalLimiter:
    """Space request starts by at least a configured monotonic interval."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_started_at: float | None = None
        self._lock = Lock()

    def wait(self) -> None:
        """Wait until the next request may start, then record its start time."""

        with self._lock:
            now = self._clock()
            if self._last_request_started_at is not None:
                elapsed = now - self._last_request_started_at
                remaining = self.minimum_interval_seconds - elapsed
                if remaining > 0:
                    self._sleeper(remaining)
            self._last_request_started_at = self._clock()
