# QA Report — issue #61 · v1

**Issue:** #61 — Define the DiscourseSource protocol and enforce channel separation  
**PR:** #73  
**Branch:** `issue-61-define-the-discoursesource-protocol-and-enforce-channel-separation`  
**Commit under test:** `829dcf6`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/02-discourse-protocol-and-invariants.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | `DiscourseSource` in `discourse/base.py` with `poll(since)` and `link_targets(item)` | Protocol surface inspection + `test_discourse_source_protocol_requires_poll_and_link_targets` | ✅ |
| AC2 | `registry.get(name)` returns adapter; unknown name raises named error | `uv run pytest tests/test_discourse_registry.py` | ✅ |
| AC3 | Channel separation: no shared base; scoring must not import discourse | `uv run pytest tests/test_channel_separation.py` | ✅ |
| AC4 | No discourse-derived value written into `claim_score` | Same suite (`test_no_discourse_value_written_to_claim_score`) | ✅ |
| AC5 | Discourse registry tests exit 0 | `uv run pytest tests/test_discourse_registry.py` | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/test_channel_separation.py tests/test_discourse_registry.py -v  # 8 passed
uv run pytest                                                                    # 282 passed
uv run ruff check .                                                              # All checks passed
uv run ruff format --check .                                                     # 116 files already formatted
```

## Evidence files

- `ac1-protocol-surface.log`
- `ac2-ac5-discourse-registry.log`
- `ac3-ac4-channel-separation.log`
- `ac-focused-pytest.log`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — protocol/registry/AST-gate task (no UI ACs).

## Notes for Reviewer

- `DiscourseSource` and `EvidenceSource` are independent `@runtime_checkable` Protocols; channel gates are AST-level and include positive detection tests.
- `link_targets` returns `list[PaperRef]` (evidence-side identity type for paper linking only) — protocols still share no custom base class.
- No discourse adapters in this PR (tasks 03/04/12).
