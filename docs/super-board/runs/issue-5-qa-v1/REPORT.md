# Issue #5 QA evidence — v1

## Result

PASS. All five acceptance criteria are covered by observable tests and passed on the
Builder branch at `ad7fb16688d0bcb286eec6959187ac5d3e7a5d5f`.

This is a non-visual Python library task. Screenshots are intentionally omitted because
none of the acceptance criteria affect a UI.

## Acceptance-criterion evidence

| AC | Observable evidence | Result |
|---|---|---|
| AC1 — registered arXiv adapter and named unknown-source error | `tests/sources/test_registry.py::test_builtin_source_is_registered_at_import_time[arxiv]`; `tests/sources/test_registry.py::test_unknown_source_raises_named_error` | PASS |
| AC2 — all three adapters implement the protocol and register at import time | `tests/sources/test_registry.py::test_builtin_source_is_registered_at_import_time` for `arxiv`, `openalex`, and `semantic_scholar` | PASS |
| AC3 — source suite passes from fixtures without live network | `uv run pytest tests/sources/ -vv`; socket-denied rerun described below | PASS — 18 tests |
| AC4 — each adapter identifies AI-Researcher and `CONTACT_EMAIL` in User-Agent | `test_user_agent_identifies_tool_and_configured_contact` in each of `test_arxiv.py`, `test_openalex.py`, and `test_semantic_scholar.py` | PASS |
| AC5 — each adapter enforces its configured minimum interval | `test_two_consecutive_calls_observe_configured_*_interval` in each adapter test module | PASS |

The tests use committed XML/JSON files under `tests/sources/fixtures/` through
`FixtureRequester`; no adapter test calls a live API.

## Commands and observed output

### Task acceptance command

```text
$ uv run pytest tests/sources/ -vv
collected 18 items
18 passed in 4.26s
exit code: 0
```

### Offline enforcement check

The source suite was run inside a Python process whose `socket.socket.connect` raises
`AssertionError` on any connection attempt:

```text
$ uv run python <socket-denied pytest harness>
..................                                                       [100%]
18 passed in 4.24s
exit code: 0
```

### Repository regression and quality gates

```text
$ uv run pytest && uv run ruff check . && uv run ruff format --check .
collected 51 items
51 passed in 6.37s
All checks passed!
37 files already formatted
exit code: 0
```

## Invariant audit

- The adapters return `PaperRef` and `PaperMetadata` dataclasses.
- The source implementation contains no database access and no LLM import or invocation.
- Crossref remains a DOI helper and is not registered as an `EvidenceSource`.
- No embedding, vector store, second database, discourse source, or other out-of-scope
  component is introduced.
