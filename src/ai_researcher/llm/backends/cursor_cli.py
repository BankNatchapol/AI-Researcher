"""Cursor CLI backend."""

import json
import os
import subprocess

from ai_researcher.llm.errors import ModelCallError, ModelOutputError, ModelTimeoutError
from ai_researcher.logging import get_logger

_logger = get_logger(__name__)

# `agent` has no --json-schema/--output-schema equivalent (unlike claude/codex), so a
# schema is requested via prompt instructions only, with no CLI-level enforcement behind
# it. Structured-output jobs routed to this backend are best-effort: a higher malformed-
# output rate than claude/codex is expected, not a bug in this backend.
_SCHEMA_INSTRUCTION_TEMPLATE = (
    "\n\nRespond with exactly one JSON object and nothing else — no prose, no "
    "markdown code fences, no explanation before or after it. The JSON object "
    "must conform to this JSON Schema:\n{schema_text}"
)


class CursorCliBackend:
    """Run a read-only, single-turn request through ``agent -p --mode ask``."""

    name = "cursor"

    def run(self, prompt: str, schema: dict | None, timeout: int) -> str | dict:
        if os.environ.get("CURSOR_API_KEY"):
            _logger.warning(
                "CURSOR_API_KEY is set; the cursor backend is designed for subscription "
                "login (agent login). Unset CURSOR_API_KEY to use the stored session only."
            )

        rendered_prompt = prompt
        if schema is not None:
            _logger.debug("cursor backend running a schema request in best-effort mode")
            schema_text = json.dumps(schema, separators=(",", ":"), sort_keys=True)
            rendered_prompt = prompt + _SCHEMA_INSTRUCTION_TEMPLATE.format(schema_text=schema_text)

        command = [
            "agent",
            "-p",
            "--mode",
            "ask",
            "--output-format",
            "json",
            "--sandbox",
            "enabled",
            rendered_prompt,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as error:
            raise ModelTimeoutError(f"cursor timed out after {timeout} seconds") from error

        if result.returncode != 0:
            detail = result.stderr.strip() or "no error output"
            raise ModelCallError(f"cursor exited with exit code {result.returncode}: {detail}")

        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as error:
            output_kind = "structured output" if schema is not None else "model output"
            raise ModelOutputError(f"cursor did not return valid {output_kind}") from error

        text = payload.get("result") if isinstance(payload, dict) else None

        if schema is None:
            if not isinstance(text, str):
                raise ModelOutputError("cursor did not return valid model output")
            return text.strip()

        structured = text
        if isinstance(structured, str):
            try:
                structured = json.loads(structured)
            except json.JSONDecodeError as error:
                raise ModelOutputError("cursor did not return valid structured output") from error
        if not isinstance(structured, dict):
            raise ModelOutputError("cursor did not return valid structured output")
        return structured
