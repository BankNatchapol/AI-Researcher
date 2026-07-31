"""Claude CLI backend."""

import json
import subprocess

from ai_researcher.llm.errors import ModelCallError, ModelOutputError, ModelTimeoutError

# Pinned rather than left to the CLI's own ambient/session default, which may be set to
# a premium model (e.g. Fable) that requires separate usage credits beyond the
# subscription this backend is meant to run under. "sonnet" is a subscription-included
# alias, not a specific dated model version.
_MODEL = "sonnet"

# A --json-schema request is answered via an internal tool call, which costs an extra
# turn beyond the plain-text case (observed 2-4 turns live, never 1) — 1 turn is enough
# for free text but reliably starves schema requests before the tool result comes back.
_SCHEMA_MAX_TURNS = "6"
_TEXT_MAX_TURNS = "1"


class ClaudeCliBackend:
    """Run a read-only, single-turn request through ``claude -p``."""

    name = "claude"

    def run(self, prompt: str, schema: dict | None, timeout: int) -> str | dict:
        command = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--max-turns",
            _SCHEMA_MAX_TURNS if schema is not None else _TEXT_MAX_TURNS,
            "--tools",
            "",
            "--model",
            _MODEL,
        ]
        if schema is not None:
            command.extend(
                [
                    "--json-schema",
                    json.dumps(schema, separators=(",", ":"), sort_keys=True),
                ]
            )
        command.extend(["--", prompt])

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
            raise ModelTimeoutError(f"claude timed out after {timeout} seconds") from error

        if result.returncode != 0:
            detail = result.stderr.strip() or "no error output"
            raise ModelCallError(f"claude exited with exit code {result.returncode}: {detail}")

        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as error:
            output_kind = "structured output" if schema is not None else "model output"
            raise ModelOutputError(f"claude did not return valid {output_kind}") from error

        if schema is None:
            text = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(text, str):
                raise ModelOutputError("claude did not return valid model output")
            return text.strip()

        structured = payload.get("structured_output") if isinstance(payload, dict) else None
        if structured is None and isinstance(payload, dict):
            structured = payload.get("result")
        if isinstance(structured, str):
            try:
                structured = json.loads(structured)
            except json.JSONDecodeError as error:
                raise ModelOutputError("claude did not return valid structured output") from error
        if not isinstance(structured, dict):
            raise ModelOutputError("claude did not return valid structured output")
        return structured
