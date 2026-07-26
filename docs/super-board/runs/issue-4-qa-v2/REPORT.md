# Issue #4 QA report — v2

## Scope

Re-verification of PR #18 at Builder rebuild commit `db3e96a` against
`docs/superpowers/projects/ai-researcher-app/phase-1/04-cli-model-gateway.md`.
The rebuild adds `--tools ""` to Claude CLI calls so the model subprocess cannot inherit
tools, plus a regression assertion for that exact flag and value.

This issue has no UI or visual acceptance criteria. Screenshots are intentionally omitted;
the evidence consists of mocked subprocess tests, static architecture checks, and repository
quality commands.

## Acceptance test plan

| AC | Observable test |
|---|---|
| AC1 | Import `ai_researcher.llm`, assert `complete` is its only exported call entry point, and exercise it through the gateway tests. |
| AC2 | Exercise an explicit normalized job override and an unmapped-job default fallback; inspect mocked subprocess arguments to keep CLI names and flags inside backend modules. |
| AC3 | Exercise plain-text and schema-constrained output through both Claude and Codex with `subprocess.run` mocked. |
| AC4 | Run `uv run pytest tests/test_gateway.py`; confirm both backends, named call/timeout/output errors, and the rebuilt Claude tool-isolation argument are covered without a real CLI invocation. |
| AC5 | Run `uv run pytest tests/test_no_direct_model_calls.py` and independently scan non-LLM application modules for direct CLI invocations or provider SDK imports. |

## Results

| AC | Result | Evidence |
|---|---|---|
| AC1 | PASS | `test_llm_package_exposes_only_complete_as_its_call_entry_point` confirms `complete` is the package's only exported model-call entry point; the gateway suite exercises it successfully. |
| AC2 | PASS | `test_claude_returns_text_for_a_plain_prompt` proves a normalized per-job override selects Claude; `test_unknown_job_uses_the_default_backend` proves an unmapped job selects the configured Codex default. Backend command assertions keep CLI details out of callers. |
| AC3 | PASS | Claude text, Claude object, Codex text, and Codex object tests all pass with subprocesses mocked. |
| AC4 | PASS | The task-mandated gateway command exits 0 with 15 tests. Named `ModelCallError`, `ModelTimeoutError`, and `ModelOutputError` paths pass for both backends. `test_claude_disables_all_tools` confirms `--tools` is followed by an empty value, and local `claude --help` identifies `--tools` as the installed CLI's tool-selection option. |
| AC5 | PASS | The task-mandated architecture guard exits 0 with 5 tests. A corrected independent source scan excluding `src/ai_researcher/llm/**` finds no direct CLI invocation or provider SDK import elsewhere. |

## Verification commands

```text
uv run pytest tests/test_gateway.py
15 passed in 0.08s

uv run pytest tests/test_no_direct_model_calls.py
5 passed in 0.01s

uv run pytest
32 passed in 2.02s

uv run ruff check .
All checks passed!

uv run ruff format --check .
21 files already formatted

rg (direct model CLI / SDK patterns outside src/ai_researcher/llm/)
No matches; command exited 0 through the absence guard.
```

## QA disposition

PASS. All five acceptance criteria remain satisfied after the rebuild, and the Reviewer
finding is covered by a focused regression test. No production or test defect was found, so
QA adds only this committed evidence report.
