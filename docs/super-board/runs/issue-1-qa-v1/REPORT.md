# Issue #1 QA report — v1

- PR: #15
- Branch: `issue-1-scaffold-python-project`
- Builder commit tested: `a7de58ce166d610406e5fe86b25c9f0247e54bf0`
- Date: 2026-07-26
- Result: PASS

## Acceptance-criterion results

| AC | Observable check | Result |
|---|---|---|
| 1 | `uv sync` completes and `uv run python --version` reports Python 3.11+ | PASS — sync exited 0 using CPython 3.11.15 |
| 2 | `uv run airesearch --help` prints usage and exits 0 | PASS — output begins with `Usage: airesearch [OPTIONS] COMMAND [ARGS]...` |
| 3 | `uv run ruff check .` and `uv run ruff format --check .` exit 0 | PASS — `All checks passed!`; 5 files already formatted |
| 4 | `uv run pytest` exits 0 and collects at least one test | PASS — 3 tests collected, 3 passed |
| 5 | Required environment keys are documented and `.env` is ignored | PASS — all four keys matched; `.gitignore:10:.env` ignores `.env` |

## Commands

```text
uv sync
uv run python --version
uv run airesearch --help
uv run ruff check .
uv run ruff format --check .
uv run pytest
test -f .env.example
rg -n '^(DATABASE_URL|GROBID_URL|LLM_BACKEND_DEFAULT|CONTACT_EMAIL)=' .env.example
git check-ignore -v .env
```

Full command output is recorded in `command-output.txt`.

## Visual evidence

Intentionally omitted: issue #1 contains only CLI, packaging, lint, test, and configuration
acceptance criteria, with no UI or visual behavior.
