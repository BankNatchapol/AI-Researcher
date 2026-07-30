# Per-AC results — issue #49 QA v1

| AC | Criterion | Evidence | Pass |
|----|-----------|----------|------|
| AC1 | claims list shows confidence and evidence_quality as separate columns | `test_render_claims_table_uses_separate_score_columns`, `test_claims_cli_lists_separate_score_columns`, sample-render-output.txt | ✅ |
| AC2 | --type / --min-confidence / --min-quality; min-quality 70 independent of confidence | `test_list_claims_filters_min_quality_independently_of_confidence`, `test_list_claims_filters_type_and_min_confidence`, `test_claims_cli_min_quality_filter_passed_through` | ✅ |
| AC3 | claim show prints claim, both score factor lists, evidence stance + rationale | `test_render_claim_detail_shows_factors_and_evidence_without_blending`, `test_claim_show_cli_prints_factors_and_evidence` | ✅ |
| AC4 | MCP list_claims / get_claim / find_claim_evidence keep distinct top-level scores | `test_mcp_claim_tools_keep_scores_as_distinct_top_level_fields` | ✅ |
| AC5 | pytest tests/test_claims_surface.py exits 0; no combined/averaged score phrasing | pytest-claims.txt (9 passed); `_assert_no_combined_score` in suite | ✅ |

**Regression:** `uv run pytest` → 266 passed; `uv run ruff check .` → clean; `uv run ruff format --check .` → clean.

**Visual evidence:** N/A — non-visual ACs (CLI/MCP only). Screenshots intentionally omitted.
