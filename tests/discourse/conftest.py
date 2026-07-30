"""Shared offline HTTP fixtures for discourse-adapter tests."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def discourse_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide complete application settings for discourse adapter tests."""

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("ARXIV_MIN_INTERVAL_SECONDS", "3")
    monkeypatch.setenv("OPENALEX_MIN_INTERVAL_SECONDS", "0.2")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("CROSSREF_MIN_INTERVAL_SECONDS", "0.1")
    monkeypatch.setenv("REDDIT_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("HACKERNEWS_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("RSS_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("HUGGINGFACE_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-client-secret")
    monkeypatch.delenv("REDDIT_SUBREDDITS", raising=False)
    monkeypatch.delenv("DISCOURSE_RSS_FEEDS", raising=False)

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
class MappingRequester:
    """HTTP requester that returns committed fixtures keyed by URL substring."""

    fixtures_by_substring: dict[str, str]
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    post_calls: list[tuple[str, dict[str, str], bytes]] = field(default_factory=list)

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.calls.append((url, headers))
        for substring, fixture_name in self.fixtures_by_substring.items():
            if substring in url:
                return (FIXTURES / fixture_name).read_bytes()
        raise LookupError(f"No fixture mapped for URL: {url}")

    def post(self, url: str, headers: dict[str, str], body: bytes) -> bytes:
        self.post_calls.append((url, headers, body))
        for substring, fixture_name in self.fixtures_by_substring.items():
            if substring in url:
                return (FIXTURES / fixture_name).read_bytes()
        raise LookupError(f"No fixture mapped for POST URL: {url}")
