"""Application settings sourced exclusively from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


class MissingConfigurationError(RuntimeError):
    """Raised when a required environment variable is absent."""


class InvalidConfigurationError(RuntimeError):
    """Raised when an environment variable has an invalid value."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for AI-Researcher."""

    database_url: str
    grobid_url: str
    llm_backend_default: str
    llm_backend_overrides: Mapping[str, str]
    llm_timeout_seconds: int
    llm_max_concurrency: int
    contact_email: str
    source_min_intervals: Mapping[str, float]
    semantic_scholar_api_key: str | None
    flaresolverr_url: str | None
    storage_dir: Path
    shortlist_backend: str
    traversal_max_nodes: int
    reddit_client_id: str | None
    reddit_client_secret: str | None
    reddit_subreddits: tuple[str, ...]
    discourse_rss_feeds: tuple[str, ...]
    discourse_scirate_enabled: bool
    discourse_scirate_arxiv_ids: tuple[str, ...]
    score_movement_threshold: int
    sweep_evidence_hour: int
    sweep_discourse_hour: int


def _required_environment_variable(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigurationError(f"Required environment variable {name} is missing")
    return value


def _positive_integer_environment_variable(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise InvalidConfigurationError(f"{name} must be a positive integer") from error
    if value < 1:
        raise InvalidConfigurationError(f"{name} must be a positive integer")
    return value


def _hour_environment_variable(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise InvalidConfigurationError(f"{name} must be an hour in 0–23") from error
    if value < 0 or value > 23:
        raise InvalidConfigurationError(f"{name} must be an hour in 0–23")
    return value


def _nonnegative_float_environment_variable(name: str, default: float) -> float:
    raw_value = os.environ.get(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise InvalidConfigurationError(f"{name} must be a non-negative number") from error
    if value < 0:
        raise InvalidConfigurationError(f"{name} must be a non-negative number")
    return value


def _llm_backend_overrides() -> Mapping[str, str]:
    prefix = "LLM_BACKEND_"
    overrides = {
        name.removeprefix(prefix): value
        for name, value in os.environ.items()
        if name.startswith(prefix) and name != "LLM_BACKEND_DEFAULT" and value
    }
    return MappingProxyType(overrides)


def _optional_environment_variable(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _reddit_subreddits() -> tuple[str, ...]:
    raw = os.environ.get("REDDIT_SUBREDDITS", "QuantumComputing,MachineLearning")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


_DEFAULT_DISCOURSE_RSS_FEEDS = (
    "https://blog.research.google/feeds/posts/default?alt=rss",
    "https://blog.research.google/feeds/posts/default/-/QuantumAI",
)


def _discourse_rss_feeds() -> tuple[str, ...]:
    raw = os.environ.get("DISCOURSE_RSS_FEEDS")
    if raw is None:
        return _DEFAULT_DISCOURSE_RSS_FEEDS
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _truthy_environment_variable(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _discourse_scirate_arxiv_ids() -> tuple[str, ...]:
    raw = os.environ.get("DISCOURSE_SCIRATE_ARXIV_IDS", "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _source_min_intervals() -> Mapping[str, float]:
    return MappingProxyType(
        {
            "arxiv": _nonnegative_float_environment_variable(
                "ARXIV_MIN_INTERVAL_SECONDS",
                default=3.0,
            ),
            "openalex": _nonnegative_float_environment_variable(
                "OPENALEX_MIN_INTERVAL_SECONDS",
                default=0.1,
            ),
            "semantic_scholar": _nonnegative_float_environment_variable(
                "SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS",
                default=1.0,
            ),
            "crossref": _nonnegative_float_environment_variable(
                "CROSSREF_MIN_INTERVAL_SECONDS",
                default=0.1,
            ),
            "reddit": _nonnegative_float_environment_variable(
                "REDDIT_MIN_INTERVAL_SECONDS",
                default=1.0,
            ),
            "hackernews": _nonnegative_float_environment_variable(
                "HACKERNEWS_MIN_INTERVAL_SECONDS",
                default=0.5,
            ),
            "rss": _nonnegative_float_environment_variable(
                "RSS_MIN_INTERVAL_SECONDS",
                default=1.0,
            ),
            "huggingface": _nonnegative_float_environment_variable(
                "HUGGINGFACE_MIN_INTERVAL_SECONDS",
                default=1.0,
            ),
            "scirate": _nonnegative_float_environment_variable(
                "SCIRATE_MIN_INTERVAL_SECONDS",
                default=5.0,
            ),
        }
    )


def get_settings() -> Settings:
    """Read and return a fresh settings object from the current environment."""

    return Settings(
        database_url=_required_environment_variable("DATABASE_URL"),
        grobid_url=_required_environment_variable("GROBID_URL"),
        llm_backend_default=_required_environment_variable("LLM_BACKEND_DEFAULT"),
        llm_backend_overrides=_llm_backend_overrides(),
        llm_timeout_seconds=_positive_integer_environment_variable(
            "LLM_TIMEOUT_SECONDS",
            default=120,
        ),
        llm_max_concurrency=_positive_integer_environment_variable(
            "LLM_MAX_CONCURRENCY",
            default=4,
        ),
        contact_email=_required_environment_variable("CONTACT_EMAIL"),
        source_min_intervals=_source_min_intervals(),
        semantic_scholar_api_key=_optional_environment_variable("SEMANTIC_SCHOLAR_API_KEY"),
        flaresolverr_url=_optional_environment_variable("FLARESOLVERR_URL"),
        storage_dir=Path(os.environ.get("STORAGE_DIR", "data/papers")),
        shortlist_backend=os.environ.get("SHORTLIST_BACKEND", "pageindex"),
        traversal_max_nodes=_positive_integer_environment_variable(
            "TRAVERSAL_MAX_NODES",
            default=40,
        ),
        reddit_client_id=_optional_environment_variable("REDDIT_CLIENT_ID"),
        reddit_client_secret=_optional_environment_variable("REDDIT_CLIENT_SECRET"),
        reddit_subreddits=_reddit_subreddits(),
        discourse_rss_feeds=_discourse_rss_feeds(),
        discourse_scirate_enabled=_truthy_environment_variable(
            "DISCOURSE_SCIRATE_ENABLED",
            default=False,
        ),
        discourse_scirate_arxiv_ids=_discourse_scirate_arxiv_ids(),
        score_movement_threshold=_positive_integer_environment_variable(
            "SCORE_MOVEMENT_THRESHOLD",
            default=10,
        ),
        sweep_evidence_hour=_hour_environment_variable("SWEEP_EVIDENCE_HOUR", default=6),
        sweep_discourse_hour=_hour_environment_variable("SWEEP_DISCOURSE_HOUR", default=7),
    )
