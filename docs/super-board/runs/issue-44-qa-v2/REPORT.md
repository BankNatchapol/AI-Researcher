# Issue #44 QA v2 report

## Result

PASS at commit `6b98be3` plus the QA continuation regression test in this evidence commit.

Issue #44 has no UI-affecting acceptance criteria. Screenshot evidence is intentionally
omitted; the observable surface is the CLI and its PostgreSQL persistence behavior.

## Acceptance-criterion evidence

1. **AC1 — all eligible papers extract and report per-paper record counts: PASS.**
   `test_extract_cli_clean_resume_prompt_bump_and_paper_failure` exercises parsed and
   abstract-only papers, asserts one gateway call per paper rather than per node, checks CLI
   count labels for claims, methods, results, datasets, and metrics, and verifies persisted
   anchors.
2. **AC2 — unchanged reruns do zero work and exit 0: PASS.**
   `test_extract_cli_clean_resume_prompt_bump_and_paper_failure` verifies the ordinary
   resumed run, while `test_valid_empty_extraction_is_resumable` verifies a valid zero-record
   run is durably current and makes no gateway calls on rerun.
3. **AC3 — every persisted assertion has model and prompt provenance: PASS.**
   `test_every_persisted_record_type_carries_extraction_provenance` checks claim, method,
   result, dataset, and metric rows and confirms pipeline-controlled values override
   untrusted model output.
4. **AC4 — prompt bumps re-extract only stale papers: PASS.**
   `test_prompt_version_bump_reextracts_only_stale_papers` marks one paper current at the new
   version and verifies only the remaining stale paper reaches the gateway.
5. **AC5 — mocked clean, resumed, bumped, and isolated-failure paths pass: PASS.**
   The issue suite covers all four paths. QA added
   `test_paper_failure_does_not_abort_remaining_stale_papers`, which verifies a failed first
   paper is retried once, the later stale paper is still extracted, and its claim is
   persisted.

## Reviewer-regression evidence

- `test_valid_empty_extraction_is_resumable`: successful empty output receives durable
  completion state; the unchanged rerun reports `extracted 0`, `skipped 2`.
- `test_all_rejected_output_does_not_replace_valid_extractions`: all-rejected output reports
  per-paper failure and preserves the prior claim IDs.
- `test_prompt_bump_preserves_claim_identity_and_dependents`: prompt re-extraction preserves
  the stable claim ID plus its `claim_evidence` and `claim_score` dependents.
- `tests/test_migrations.py`: the full suite applies migration
  `0006_extraction_state`, checks the table/model shape, and verifies migration idempotency.

## Commands

```text
uv run pytest tests/test_extraction_pipeline.py
9 passed in 1.60s

uv run pytest
180 passed in 11.37s

uv run ruff check .
All checks passed!

uv run ruff format --check .
93 files already formatted
```

