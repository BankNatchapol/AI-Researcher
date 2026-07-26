"""Single public boundary for all model calls."""

import threading

from ai_researcher.config import get_settings
from ai_researcher.llm.errors import ModelCallError
from ai_researcher.llm.registry import resolve_backend

__all__ = ["complete"]

_semaphore_lock = threading.Lock()
_semaphores: dict[int, threading.BoundedSemaphore] = {}


def _semaphore(capacity: int) -> threading.BoundedSemaphore:
    with _semaphore_lock:
        return _semaphores.setdefault(capacity, threading.BoundedSemaphore(capacity))


def _render_prompt(messages: list[dict]) -> str:
    rendered_messages: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ModelCallError("Each message must contain string role and content values")
        rendered_messages.append(f"{role.upper()}:\n{content}")
    if not rendered_messages:
        raise ModelCallError("At least one message is required")
    return "\n\n".join(rendered_messages)


def complete(
    messages: list[dict],
    job: str,
    schema: dict | None = None,
    timeout: int | None = None,
) -> str | dict:
    """Run one bounded, non-agentic model request for ``job``."""

    settings = get_settings()
    effective_timeout = settings.llm_timeout_seconds if timeout is None else timeout
    if effective_timeout < 1:
        raise ModelCallError("Model timeout must be a positive number of seconds")
    backend = resolve_backend(job, settings)
    prompt = _render_prompt(messages)

    with _semaphore(settings.llm_max_concurrency):
        try:
            return backend.run(prompt, schema, effective_timeout)
        except ModelCallError:
            raise
        except Exception as error:
            raise ModelCallError(f"Model backend failed: {error}") from error
