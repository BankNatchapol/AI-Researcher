# Issue #7 QA report — v1

- PR: #21
- Branch: `issue-7-build-the-interactive-topic-scoping-dialogue-and-scope-cli`
- Implementation commit tested: `dd3868104ada5c882afad8f2936382acc97868ed`
- Base commit: `22733175adfaf1334447a1fcb5bf538b3da85711`
- Task contract:
  `docs/superpowers/projects/ai-researcher-app/phase-1/07-topic-scoping-dialogue.md`
- Test type: offline CLI, dialogue, adapter-fixture, and persistence-unit verification

## Issue-scoped test plan

| AC | Observable proof | Automated coverage |
|---|---|---|
| AC1 | `scope new` displays all three proposal classes and sends exactly one narrowed definition to the persistence boundary | `test_scope_new_runs_dialogue_and_persists_exactly_one_row` |
| AC2 | An estimate appears before narrowing and after every accepted decision | `test_dialogue_estimates_before_narrowing_and_after_each_accepted_decision` |
| AC3 | `scope show` displays include/exclude terms, arXiv categories, date range, per-source limit, and estimated size | `test_scope_show_prints_the_full_definition_and_current_estimate` |
| AC4 | `scope list` displays every fixture scope and its current estimated size | `test_scope_list_prints_every_scope_with_its_estimated_size` |
| AC5 | The stated offline command collects and passes all scoping tests while the LLM and adapter counts are controlled | `uv run pytest tests/test_scoping.py` |

Supporting coverage also verifies that estimation calls lightweight capped
`EvidenceSource.search` methods across every registered adapter, deduplicates shared
results, and raises immediately if metadata or PDF retrieval is attempted.

## Independent CLI exercise

The CLI was invoked through Typer's `CliRunner` with a deterministic structured LLM
proposal, deterministic adapter estimates, and an in-memory persistence boundary.

```text
=== AC1 + AC2: scope new ===
Estimated candidates before narrowing: 120
Proposed sub-topic: surface code thresholds
Accept sub-topic 'surface code thresholds'? [y/N]: y
Estimated candidates after accepting sub-topic 'surface code thresholds': 80
Proposed adjacent term: fault tolerant architectures
Accept adjacent term 'fault tolerant architectures'? [y/N]: y
Estimated candidates after accepting adjacent term 'fault tolerant architectures': 55
Proposed exclusion: biomedical sensing
Accept exclusion 'biomedical sensing'? [y/N]: y
Estimated candidates after accepting exclusion 'biomedical sensing': 30
Saved scope 'surface-codes'.

=== AC3: scope show ===
Name: surface-codes
Description: Quantum error correction
Include terms: Quantum error correction, surface code thresholds, fault tolerant architectures
Exclude terms: biomedical sensing
arXiv categories: quant-ph
Date range: 2020-01-01 to 2025-12-31
Per-source limit: 50
Estimated corpus size: 30

=== AC4: scope list ===
Name    Estimated corpus size
surface-codes   30

Observed persisted rows: 1
```

## Verification

Fresh final branch-state verification:

| Command | Result |
|---|---|
| `uv run pytest tests/test_scoping.py` | PASS — 7 passed |
| `uv run pytest` | PASS — 65 passed |
| `uv run ruff check .` | PASS — all checks passed |
| `uv run ruff format --check .` | PASS — 45 files already formatted |
| `git diff --check` | PASS — no whitespace errors |

## Visual evidence

Screenshots are intentionally omitted. Issue #7 changes a local CLI and persistence
library only; it has no UI or visual acceptance criterion. The terminal transcript above
is the observable evidence required for this non-visual task.

## Findings

No acceptance-criterion failures or QA-owned test gaps were observed during issue-scoped
testing.
