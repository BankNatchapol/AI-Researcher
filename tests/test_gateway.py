"""Tests for the non-agentic CLI model gateway."""

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide complete settings and isolate per-job backend overrides."""

    for name in tuple(os.environ):
        if name.startswith("LLM_BACKEND_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "37")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "4")


def _gateway_modules():
    from ai_researcher.llm import gateway
    from ai_researcher.llm.errors import ModelCallError, ModelOutputError, ModelTimeoutError

    return gateway, ModelCallError, ModelOutputError, ModelTimeoutError


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _write_codex_result(command: list[str], content: str) -> None:
    output_path = Path(command[command.index("--output-last-message") + 1])
    output_path.write_text(content, encoding="utf-8")


def test_codex_returns_text_for_a_plain_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _, _, _ = _gateway_modules()

    def fake_run(command: list[str], **kwargs):
        _write_codex_result(command, "A plain answer.\n")
        assert command[:5] == ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check"]
        assert "--output-schema" not in command
        assert command[-1] == "USER:\nExplain the result."
        assert kwargs["timeout"] == 37
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = gateway.complete([{"role": "user", "content": "Explain the result."}], "answer")

    assert result == "A plain answer."


def test_codex_returns_an_object_for_a_schema_request(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _, _, _ = _gateway_modules()
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    def fake_run(command: list[str], **kwargs):
        del kwargs
        schema_path = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema_path.read_text(encoding="utf-8")) == schema
        _write_codex_result(command, '{"answer": "structured"}')
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = gateway.complete(
        [{"role": "user", "content": "Return an answer."}],
        "extract",
        schema=schema,
    )

    assert result == {"answer": "structured"}


def test_claude_returns_text_for_a_plain_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, _, _, _ = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_SUMMARIZE_TREE", "claude")
    run = Mock(return_value=_completed(json.dumps({"result": "Claude answer"})))
    monkeypatch.setattr(subprocess, "run", run)

    result = gateway.complete([{"role": "user", "content": "Summarize."}], "summarize-tree")

    assert result == "Claude answer"
    command = run.call_args.args[0]
    assert command[:6] == ["claude", "-p", "--output-format", "json", "--max-turns", "1"]
    assert command[-1] == "USER:\nSummarize."


def test_claude_disables_all_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _, _, _ = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "claude")
    run = Mock(return_value=_completed(json.dumps({"result": "Read-only answer"})))
    monkeypatch.setattr(subprocess, "run", run)

    gateway.complete([{"role": "user", "content": "Answer without tools."}], "answer")

    command = run.call_args.args[0]
    tools_index = command.index("--tools")
    assert command[tools_index + 1] == ""


def test_claude_returns_an_object_for_a_schema_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, _, _, _ = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_EXTRACT", "claude")
    schema = {"type": "object", "properties": {"claim": {"type": "string"}}}
    run = Mock(
        return_value=_completed(json.dumps({"structured_output": {"claim": "A grounded claim"}}))
    )
    monkeypatch.setattr(subprocess, "run", run)

    result = gateway.complete(
        [{"role": "user", "content": "Extract."}],
        "extract",
        schema=schema,
        timeout=9,
    )

    assert result == {"claim": "A grounded claim"}
    command = run.call_args.args[0]
    assert command[command.index("--json-schema") + 1] == json.dumps(
        schema, separators=(",", ":"), sort_keys=True
    )
    assert run.call_args.kwargs["timeout"] == 9


@pytest.mark.parametrize("backend", ["claude", "codex"])
def test_nonzero_cli_exit_raises_model_call_error(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    gateway, ModelCallError, _, _ = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", backend)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=_completed(stderr="subscription unavailable", returncode=23)),
    )

    with pytest.raises(ModelCallError, match=r"exit code 23.*subscription unavailable"):
        gateway.complete([{"role": "user", "content": "Hello"}], "answer")


@pytest.mark.parametrize("backend", ["claude", "codex"])
def test_cli_timeout_raises_model_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    gateway, _, _, ModelTimeoutError = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", backend)
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired([backend], timeout=5)),
    )

    with pytest.raises(ModelTimeoutError, match=rf"{backend}.*5 seconds"):
        gateway.complete(
            [{"role": "user", "content": "Hello"}],
            "answer",
            timeout=5,
        )


@pytest.mark.parametrize(
    ("backend", "stdout"),
    [
        ("claude", "not-json"),
        ("codex", "not-json"),
    ],
)
def test_malformed_schema_output_raises_model_output_error(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    stdout: str,
) -> None:
    gateway, _, ModelOutputError, _ = _gateway_modules()
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", backend)

    def fake_run(command: list[str], **kwargs):
        del kwargs
        if backend == "codex":
            _write_codex_result(command, stdout)
            return _completed()
        return _completed(stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ModelOutputError, match="valid structured output"):
        gateway.complete(
            [{"role": "user", "content": "Hello"}],
            "extract",
            schema={"type": "object"},
        )


def test_unknown_job_uses_the_default_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _, _, _ = _gateway_modules()

    def fake_run(command: list[str], **kwargs):
        del kwargs
        assert command[0] == "codex"
        _write_codex_result(command, "fallback")
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert gateway.complete([{"role": "user", "content": "Hello"}], "unmapped-job") == "fallback"


def test_gateway_caps_parallel_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _, _, _ = _gateway_modules()
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "1")
    first_entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = 0
    peak_active = 0

    class BlockingBackend:
        def run(self, prompt: str, schema: dict | None, timeout: int) -> str:
            nonlocal active, peak_active
            del prompt, schema, timeout
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            first_entered.set()
            assert release.wait(timeout=2)
            with lock:
                active -= 1
            return "done"

    monkeypatch.setattr(gateway, "resolve_backend", lambda job, settings: BlockingBackend())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(gateway.complete, [{"role": "user", "content": "Hi"}], "answer")
            for _ in range(2)
        ]
        assert first_entered.wait(timeout=1)
        time.sleep(0.05)
        assert peak_active == 1
        release.set()
        assert [future.result(timeout=1) for future in futures] == ["done", "done"]


def test_llm_package_exposes_only_complete_as_its_call_entry_point() -> None:
    import ai_researcher.llm as llm

    assert llm.__all__ == ["complete"]
    assert llm.complete is not None


def test_unexpected_backend_failure_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, ModelCallError, _, _ = _gateway_modules()
    backend = SimpleNamespace(run=Mock(side_effect=OSError("executable missing")))
    monkeypatch.setattr(gateway, "resolve_backend", lambda job, settings: backend)

    with pytest.raises(ModelCallError, match="executable missing"):
        gateway.complete([{"role": "user", "content": "Hi"}], "answer")
