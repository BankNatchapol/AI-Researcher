"""Claude CLI backend."""

import json
import subprocess

from ai_researcher.llm.errors import ModelCallError, ModelOutputError, ModelTimeoutError


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
            "1",
            "--tools",
            "",
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
