---
title: Add the LiteLLM gateway as the single model-call boundary
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

Every model call in the codebase routes through one gateway module, with model names read
from configuration, enforced by a test that fails if any other module imports LiteLLM.

## Acceptance Criteria

- [ ] `ai_researcher.llm.gateway.complete(messages, job)` returns model output and is the only public model-call entry point
- [ ] Model names resolve from config by job type, with no model string literal at any call site
- [ ] `uv run pytest tests/test_no_direct_litellm.py` exits 0, proving `src/ai_researcher/llm/gateway.py` is the only file importing `litellm`
- [ ] `uv run pytest tests/test_gateway.py` exits 0, covering a successful call and a provider error surfaced as a named application error
- [ ] A missing API key raises a named configuration error naming the missing variable, not a raw provider exception

## Implementation notes

**Files:**
- Create: `src/ai_researcher/llm/__init__.py`
- Create: `src/ai_researcher/llm/gateway.py` — wraps `litellm.completion`; signature `complete(messages: list[dict], job: str, **kwargs) -> str`; `job` selects the configured model
- Modify: `src/ai_researcher/config.py` — add `LLM_MODEL_DEFAULT` plus per-job overrides such as `LLM_MODEL_SCOPING`
- Modify: `.env.example` — document every model variable
- Test: `tests/test_gateway.py` — mocks LiteLLM, asserts routing and error translation
- Test: `tests/test_no_direct_litellm.py` — walks `src/ai_researcher/`, asserts no file other than `llm/gateway.py` contains `import litellm` or `from litellm`

**Interfaces:**
- Consumes: `ai_researcher.config` (task 01)
- Produces: `complete()` — used by task 07's scoping dialogue, Phase 2 node summaries and traversal, Phase 3 extraction

## Out of scope

No retries with backoff, no cost tracking, no streaming, no local model support. No caching
layer — Phase 2 owns tree caching. Do not call the gateway from any other module in this
task; task 07 is the first consumer.
