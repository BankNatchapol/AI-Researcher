# Issue #4 QA report — v3

## Scope

Re-verification of PR #18 at Builder rebuild commit `c4f8ab4` against
`docs/superpowers/projects/ai-researcher-app/phase-1/04-cli-model-gateway.md`.
The rebuild terminates Claude CLI option parsing with `--` immediately before the
positional prompt, preventing the variadic `--tools` option from consuming prompt text.

This issue has no UI or visual acceptance criteria. Screenshots are intentionally omitted;
the evidence consists of mocked subprocess tests, static architecture checks, installed CLI
help, and repository quality commands.

## Acceptance test plan

| AC | Observable test |
|---|---|
| AC1 | Import `ai_researcher.llm`, assert `complete` is its only exported call entry point, and exercise requests through that gateway. |
| AC2 | Exercise a normalized per-job override and an unmapped-job default fallback; inspect mocked subprocess arguments to prove CLI details stay inside backend modules. |
| AC3 | Exercise plain-text and schema-constrained output through both Claude and Codex, and assert Claude's positional prompt follows an explicit `--` option terminator. |
| AC4 | Run `uv run pytest tests/test_gateway.py`; confirm both backends, named call/timeout/output errors, concurrency, tool isolation, and prompt ordering are covered with `subprocess.run` mocked. |
| AC5 | Run `uv run pytest tests/test_no_direct_model_calls.py` and independently scan non-LLM application modules for direct CLI invocations or provider SDK imports. |

## Results

| AC | Result | Evidence |
|---|---|---|
| AC1 | PASS | `test_llm_package_exposes_only_complete_as_its_call_entry_point` confirms `complete` is the package's only exported model-call entry point; the gateway suite exercises it successfully. |
| AC2 | PASS | `test_claude_returns_text_for_a_plain_prompt` proves a normalized job override selects Claude; `test_unknown_job_uses_the_default_backend` proves an unmapped job selects the configured Codex default. CLI argument assertions remain confined to backend tests. |
| AC3 | PASS | Claude text/object and Codex text/object tests pass. `test_claude_terminates_variadic_tools_before_prompt` proves the final argv pair is `["--", "USER:\nSENTINEL_PROMPT"]`; installed `claude --help` confirms `--tools <tools...>` is variadic. |
| AC4 | PASS | The task-mandated gateway command exits 0 with 16 tests. Named `ModelCallError`, `ModelTimeoutError`, and `ModelOutputError` paths pass for both backends; all subprocess calls are mocked. |
| AC5 | PASS | The task-mandated architecture guard exits 0 with 5 tests. An independent scan excluding `src/ai_researcher/llm/**` finds no direct CLI invocation or provider SDK import elsewhere. |

## Verification commands

```text
uv run pytest tests/test_gateway.py
16 passed in 0.08s

uv run pytest tests/test_no_direct_model_calls.py
5 passed in 0.01s

uv run pytest
33 passed in 2.13s

uv run ruff check .
All checks passed!

uv run ruff format --check .
21 files already formatted

git diff --check origin/main...HEAD
No output; exit 0.

rg (direct model CLI / SDK patterns outside src/ai_researcher/llm/)
No matches; absence guard exited 0.

claude --help | rg -- '--tools|--json-schema|--max-turns|--output-format'
Installed help reports `--tools <tools...>`, `--json-schema`, and `--output-format`.
```

## QA disposition

PASS. All five acceptance criteria remain satisfied after Builder rebuild 2, and the exact
argument-order regression that prompted the rebuild is covered. No production or test defect
was found, so QA adds only this committed evidence report.
