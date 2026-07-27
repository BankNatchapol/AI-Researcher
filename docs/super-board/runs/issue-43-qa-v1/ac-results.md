# Per-AC results — issue #43 QA v1

| AC | Criterion | Command / test | Expected | Actual | Pass |
|----|-----------|----------------|----------|--------|------|
| AC1 | Pydantic models for claim/method/result/dataset/metric each require non-empty tree_node_id | `test_models_require_non_empty_tree_node_id` | All 5 models validate with id=1; None/missing raise | PASSED | ✅ |
| AC2 | Missing tree_node_id → named error, logged, never persisted | `test_missing_tree_node_id_is_named_error_and_logged` | MissingAnchorError + WARNING log; accepted=[] | PASSED | ✅ |
| AC3 | Numeric claims split object_value/unit (`"1%"` → 1, `%`) | `test_parse_quantity_*` + `test_valid_record_passes_validation` | 1%→(1,%); 0.01→(0.01,None); 1e-2→(0.01,None) | PASSED | ✅ |
| AC4 | Malformed LLM output retried once, then paper_failed without raising | `test_unparseable_json_retries_once_then_paper_failure_without_raising` | 2 fetch calls; paper_failed=True; no exception | PASSED | ✅ |
| AC5 | `uv run pytest tests/test_extraction_validation.py` exits 0 with required coverage | full file (9 tests) | exit 0 | 9 passed | ✅ |

Also covered: foreign tree_node_id rejection (`test_foreign_tree_node_id_is_rejected_and_logged`) and retry-then-accept path.

**Visual evidence:** N/A — non-visual ACs (unit/API validation only). Screenshots intentionally omitted.

**Regression:** `uv run pytest` → 170 passed; `uv run ruff check .` → clean; `uv run ruff format --check .` → clean.
