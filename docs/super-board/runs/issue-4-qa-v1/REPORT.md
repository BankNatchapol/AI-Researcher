# Issue #4 QA report — v1

## Scope

Non-visual verification of PR #18 against
`docs/superpowers/projects/ai-researcher-app/phase-1/04-cli-model-gateway.md`.
Screenshots are intentionally omitted because every acceptance criterion concerns Python
API behavior, subprocess isolation, configuration, or static architecture.

## Acceptance test plan

| AC | Observable test |
|---|---|
| AC1 | Import `ai_researcher.llm`, confirm `complete` is its only exported call entry point, and exercise it through the mocked gateway suite. |
| AC2 | Exercise an explicit normalized per-job override and an unmapped-job fallback, then inspect mocked subprocess arguments to confirm callers supply no CLI details. |
| AC3 | Exercise plain-text and schema-constrained responses through both Claude and Codex backends with `subprocess.run` mocked. |
| AC4 | Run the task-mandated gateway test command and confirm named call, timeout, and malformed-output exceptions for both backends without a real CLI process. |
| AC5 | Run the task-mandated architecture guard and independently search application source for direct CLI/SDK references outside `ai_researcher/llm/`. |

## Results

| AC | Result | Evidence |
|---|---|---|
| AC1 | PASS | `test_llm_package_exposes_only_complete_as_its_call_entry_point` confirms `complete` is the package's only exported call entry point; the gateway suite exercises that entry point successfully. |
| AC2 | PASS | `test_claude_returns_text_for_a_plain_prompt` proves a normalized `summarize-tree` job override selects Claude; `test_unknown_job_uses_the_default_backend` proves an unmapped job selects the configured Codex default. Mock command assertions keep CLI names and flags inside the backend layer. |
| AC3 | PASS | Four backend/response-shape tests cover Claude text, Claude object, Codex text, and Codex object results. |
| AC4 | PASS | `uv run pytest tests/test_gateway.py` exited 0 with 14 passed. The suite mocks `subprocess.run` and covers both backends plus named call, timeout, and malformed-output errors. |
| AC5 | PASS | `uv run pytest tests/test_no_direct_model_calls.py` exited 0 with 5 passed. An independent `rg` scan for direct Claude/Codex invocations and LiteLLM/OpenAI/Anthropic imports outside `src/ai_researcher/llm/` returned no matches. |

## Verification commands

```text
uv run pytest tests/test_gateway.py
14 passed in 0.08s

uv run pytest tests/test_no_direct_model_calls.py
5 passed in 0.00s

uv run pytest
31 passed in 2.17s

uv run ruff check .
All checks passed!

uv run ruff format --check .
21 files already formatted
```

## QA disposition

PASS. All five task acceptance criteria are observable and satisfied. No production or test
defect was found, so QA adds only this committed evidence report.
