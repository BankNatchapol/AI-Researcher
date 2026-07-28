# Issue #44 QA evidence — v1

- Issue: #44 — Run the per-paper extraction pipeline with resumability and prompt versioning
- PR: #53
- Branch: `issue-44-extraction-pipeline`
- Result: PASS
- Evidence type: automated CLI and PostgreSQL integration tests
- Visual evidence: intentionally omitted; this issue has no UI-affecting acceptance criteria

## Acceptance-criterion test plan

| AC | Observable check | Result |
|---|---|---|
| AC1 | `test_extract_cli_clean_resume_prompt_bump_and_paper_failure` invokes `airesearch extract surface-codes`, verifies both eligible papers are processed, checks per-paper counts for claims/methods/results/datasets/metrics, and proves gateway calls scale with papers rather than nodes. | PASS |
| AC2 | The same integration test invokes the command again without new papers or a prompt change, observes exit code 0, `extracted 0`, `skipped 2`, and no additional gateway calls. | PASS |
| AC3 | `test_every_persisted_record_type_carries_extraction_provenance` queries all five extraction tables and verifies every row has pipeline-controlled `extraction_model` and `prompt_version`, even when the mocked model returns untrusted provenance values. | PASS |
| AC4 | `test_prompt_version_bump_reextracts_only_stale_papers` marks one paper current at prompt version 2, bumps `PROMPT_VERSION`, and verifies only the stale paper reaches the gateway (`extracted 1`, `skipped 1`). | PASS |
| AC5 | `test_extract_cli_clean_resume_prompt_bump_and_paper_failure` covers a clean run, resume, prompt bump, and a simulated per-paper gateway failure that does not abort the command. The exact task command passes with the LLM mocked. | PASS |

## Test-first proof for QA additions

The two QA-added tests were run against `origin/main` in a detached temporary worktree before
the PR branch was accepted. Both failed because the extraction prompt/pipeline feature does
not exist on the base revision (`EXPECTED_BASELINE_TEST_EXIT=1`). On PR #53 they pass.

## Fresh verification

```text
$ uv run pytest tests/test_extraction_pipeline.py
5 passed in 0.90s

$ uv run pytest
176 passed in 10.38s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
93 files already formatted
```

The integration tests used the repository's PostgreSQL test service and mocked
`ai_researcher.llm.gateway.complete`; no provider call or API key was used.
