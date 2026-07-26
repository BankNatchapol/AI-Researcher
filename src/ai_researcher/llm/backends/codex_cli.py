"""Codex CLI backend."""

import json
import subprocess
import tempfile
from pathlib import Path

from ai_researcher.llm.errors import ModelCallError, ModelOutputError, ModelTimeoutError


class CodexCliBackend:
    """Run a read-only request through ``codex exec``."""

    name = "codex"

    def run(self, prompt: str, schema: dict | None, timeout: int) -> str | dict:
        with tempfile.TemporaryDirectory(prefix="ai-researcher-codex-") as directory:
            temporary_directory = Path(directory)
            output_path = temporary_directory / "last-message.txt"
            command = [
                "codex",
                "exec",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--output-last-message",
                str(output_path),
            ]
            if schema is not None:
                schema_path = temporary_directory / "output-schema.json"
                schema_path.write_text(
                    json.dumps(schema, separators=(",", ":"), sort_keys=True),
                    encoding="utf-8",
                )
                command.extend(["--output-schema", str(schema_path)])
            command.append(prompt)

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as error:
                raise ModelTimeoutError(f"codex timed out after {timeout} seconds") from error

            if result.returncode != 0:
                detail = result.stderr.strip() or "no error output"
                raise ModelCallError(f"codex exited with exit code {result.returncode}: {detail}")

            try:
                output = output_path.read_text(encoding="utf-8").strip()
            except OSError as error:
                raise ModelOutputError("codex did not return valid model output") from error

        if schema is None:
            if not output:
                raise ModelOutputError("codex did not return valid model output")
            return output

        try:
            structured = json.loads(output)
        except json.JSONDecodeError as error:
            raise ModelOutputError("codex did not return valid structured output") from error
        if not isinstance(structured, dict):
            raise ModelOutputError("codex did not return valid structured output")
        return structured
