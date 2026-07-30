# QA Report — issue #49 v1

Date: 2026-07-30
Branch: issue-49-expose-claims-through-the-cli-and-mcp-with-both-scores-shown-separately
Builder commit: 85793b7
PR: https://github.com/BankNatchapol/AI-Researcher/pull/58
Result: **PASS**

## Scope

Non-visual ACs (CLI + MCP + unit tests). No UI — screenshots intentionally omitted.

## Acceptance Criteria plan

| AC | Observable test | Result |
|----|-----------------|--------|
| AC1 | `claims --scope` table has separate `confidence` and `evidence_quality` columns | PASS |
| AC2 | `--type` / `--min-confidence` / `--min-quality`; `--min-quality 70` ignores confidence | PASS |
| AC3 | `claim show <id>` prints claim, both scores + factors, evidence with stance/rationale | PASS |
| AC4 | MCP `list_claims` / `get_claim` / `find_claim_evidence` keep scores as distinct top-level fields | PASS |
| AC5 | `uv run pytest tests/test_claims_surface.py` exits 0 incl. no-combined-score assertion | PASS (9) |

## Commands

```text
uv run pytest tests/test_claims_surface.py -v   # 9 passed
uv run pytest                                   # 266 passed
uv run ruff check .                             # All checks passed
uv run ruff format --check .                    # 108 files already formatted
```

## Invariant spot-check

- Score columns/fields never blended, averaged, or combined under one heading.
- `--min-quality` filters on `evidence_quality` only (high confidence + low quality excluded).
- MCP payloads expose `confidence` and `evidence_quality` as separate keys; no `combined_score`.
- No embeddings / discourse imports in claims surface.

## Visual evidence

Intentionally omitted — CLI/MCP/library task with no UI surface.
