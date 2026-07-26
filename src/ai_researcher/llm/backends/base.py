"""Backend contract used by the model gateway."""

from typing import Protocol


class Backend(Protocol):
    """Run one non-agentic model request."""

    def run(self, prompt: str, schema: dict | None, timeout: int) -> str | dict:
        """Return plain text or a schema-constrained object."""

        ...
