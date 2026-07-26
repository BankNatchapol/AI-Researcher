---
title: Add the CLI subprocess gateway as the single model-call boundary
order: 4
depends_on_task: 03-migration-runner-and-schema
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 7
skills: test-driven-development, verification-before-completion
---

## Goal

Every model call in the codebase routes through one gateway module that shells out to the
`claude` or `codex` CLI — selectable per job type — so the app runs on CLI subscriptions
with no provider API key anywhere.

## Acceptance Criteria

- [ ] `ai_researcher.llm.gateway.complete(messages, job)` returns model output and is the only public model-call entry point
- [ ] Backend and CLI are resolved per `job` from config; a job with no explicit mapping falls back to `LLM_BACKEND_DEFAULT`, and no CLI name or flag appears at any call site
- [ ] Both backends work: `claude -p` and `codex exec`, each returning parsed text for a plain prompt and a parsed object for a schema-constrained request
- [ ] `uv run pytest tests/test_gateway.py` exits 0, covering both backends, a non-zero CLI exit surfaced as a named `ModelCallError`, a timeout surfaced as `ModelTimeoutError`, and malformed output surfaced as `ModelOutputError` — all with the subprocess mocked, no real CLI invoked
- [ ] `uv run pytest tests/test_no_direct_model_calls.py` exits 0, proving no module outside `ai_researcher/llm/` invokes `claude` or `codex` or imports an LLM SDK

## Implementation notes

**Files:**
- Create: `src/ai_researcher/llm/__init__.py`
- Create: `src/ai_researcher/llm/gateway.py` — public `complete(messages: list[dict], job: str, schema: dict | None = None, timeout: int | None = None) -> str | dict`; resolves the backend for `job`, delegates, translates errors
- Create: `src/ai_researcher/llm/backends/base.py` — `Backend` protocol: `run(prompt: str, schema: dict | None, timeout: int) -> str | dict`
- Create: `src/ai_researcher/llm/backends/claude_cli.py` — `claude -p --output-format json --max-turns 1`
- Create: `src/ai_researcher/llm/backends/codex_cli.py` — `codex exec --sandbox read-only --skip-git-repo-check`, plus `--output-schema <tmpfile>` when a schema is given and `--output-last-message <tmpfile>` to read the result
- Create: `src/ai_researcher/llm/registry.py` — job → backend resolution from config
- Create: `src/ai_researcher/llm/errors.py` — `ModelCallError`, `ModelTimeoutError`, `ModelOutputError`
- Modify: `src/ai_researcher/config.py` — add `LLM_BACKEND_DEFAULT` plus optional `LLM_BACKEND_<JOB>` overrides, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_CONCURRENCY`
- Modify: `.env.example` — document every variable added here; remove `LLM_MODEL_DEFAULT` if present, since model choice now belongs to the CLI's own configuration
- Test: `tests/test_gateway.py`
- Test: `tests/test_no_direct_model_calls.py` — walks `src/ai_researcher/`, asserts no file outside `llm/` contains `claude -p`, `codex exec`, `import litellm`, `import openai`, or `import anthropic`

**Interfaces:**
- Consumes: `ai_researcher.config`
- Produces: `complete()` — used by task 07's scoping dialogue, and by Phase 2 node summaries, shortlisting, traversal, and synthesis, and Phase 3 extraction, stance, and dedup

**Why subprocess and not an API SDK:** access is via CLI subscription, not a provider API key.
There is no key to give an SDK. `claude -p` and `codex exec` are documented non-interactive
modes that authenticate through the existing subscription.

**Sandbox and turn limits are deliberate.** These calls want text back, not an agent that
edits the repo. `codex exec` runs `--sandbox read-only`; `claude -p` runs `--max-turns 1`.
A gateway call must never be able to modify the working tree.

**Concurrency and timeouts.** Every call takes a timeout (default from
`LLM_TIMEOUT_SECONDS`, 120). The gateway caps parallel subprocesses at
`LLM_MAX_CONCURRENCY` (default 4) via a semaphore, so batch jobs in later phases can fan out
without spawning hundreds of CLI processes.

**Batching is the caller's job, but the gateway must not obstruct it.** `complete()` accepts
one prompt and returns one result; callers batch many items into a single prompt. Do not add
a convenience helper that loops per item — at CLI latency that is the difference between an
overnight job and an infeasible one.

## Out of scope

No LiteLLM, no provider SDK, no API keys — recorded as the escape hatch if API access is
ever obtained, not built now. No retries with backoff, no cost tracking, no streaming, no
response caching. Do not call the gateway from any other module in this task; task 07 is the
first consumer.
