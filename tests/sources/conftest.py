"""Shared offline HTTP fixtures for evidence-source adapter tests."""

import os
from dataclasses import dataclass, field
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.response import addinfourl

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def source_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide complete application settings with test-sized source intervals."""

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("ARXIV_MIN_INTERVAL_SECONDS", "3")
    monkeypatch.setenv("OPENALEX_MIN_INTERVAL_SECONDS", "0.2")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("CROSSREF_MIN_INTERVAL_SECONDS", "0.1")

    for name in tuple(os.environ):
        if name.startswith("LLM_BACKEND_") and name != "LLM_BACKEND_DEFAULT":
            monkeypatch.delenv(name)


@dataclass
class FakeClock:
    """Controllable monotonic clock and sleeper used to prove spacing."""

    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class FixtureRequester:
    """HTTP requester that can only return a committed fixture."""

    fixture_name: str
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.calls.append((url, headers))
        return (FIXTURES / self.fixture_name).read_bytes()


@dataclass
class FixturePostRequester:
    """POST requester that can only return a committed fixture."""

    fixture_name: str
    calls: list[tuple[str, dict[str, str], bytes]] = field(default_factory=list)

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> bytes:
        self.calls.append((url, headers, body))
        return (FIXTURES / self.fixture_name).read_bytes()


@dataclass
class SequencedResponses:
    """Plays back a scripted sequence of bytes/Exception, one per call.

    Works as either a 2-arg Requester or a 3-arg PostRequester, since ``body`` is
    optional and unused for GET-shaped calls.
    """

    responses: list[bytes | Exception]
    calls: list[tuple] = field(default_factory=list)

    def __call__(self, url: str, headers: dict[str, str], body: bytes | None = None) -> bytes:
        self.calls.append((url, headers) if body is None else (url, headers, body))
        outcome = self.responses[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_http_error(url: str, code: int, *, retry_after: str | None = None) -> HTTPError:
    """Build a realistic HTTPError, optionally carrying a Retry-After header."""

    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError(
        url,
        code,
        "",
        hdrs=headers,
        fp=addinfourl(BytesIO(b""), {}, url),
    )
