"""Resolve a configured job type to its CLI backend."""

import re

from ai_researcher.config import Settings
from ai_researcher.llm.backends.base import Backend
from ai_researcher.llm.backends.claude_cli import ClaudeCliBackend
from ai_researcher.llm.backends.codex_cli import CodexCliBackend
from ai_researcher.llm.errors import ModelCallError

_BACKENDS: dict[str, type[Backend]] = {
    "claude": ClaudeCliBackend,
    "codex": CodexCliBackend,
}


def _normalized_job(job: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", job).strip("_").upper()
    if not normalized:
        raise ModelCallError("Model job must contain at least one letter or number")
    return normalized


def resolve_backend(job: str, settings: Settings) -> Backend:
    """Return the backend configured for ``job``, falling back to the default."""

    backend_name = settings.llm_backend_overrides.get(
        _normalized_job(job),
        settings.llm_backend_default,
    ).lower()
    backend_type = _BACKENDS.get(backend_name)
    if backend_type is None:
        raise ModelCallError(
            f"Unsupported model backend {backend_name!r} configured for job {job!r}"
        )
    return backend_type()
