# QA Report — issue #62 · v1

**Issue:** #62 — Implement the Reddit and Hacker News discourse adapters  
**PR:** #74  
**Branch:** `issue-62-implement-the-reddit-and-hacker-news-discourse-adapters`  
**Commit under test:** `18f04d9`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/03-reddit-hackernews-adapters.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | Both adapters implement `DiscourseSource` and are registered | `test_*_implements_discourse_source_and_is_registered` | ✅ |
| AC2 | Reddit OAuth via env creds; default `r/QuantumComputing` + `r/MachineLearning` | OAuth poll test + config defaults probe | ✅ |
| AC3 | Missing Reddit creds → skip log + empty (no raise / exit 0 path) | `test_missing_credentials_skips_with_log_and_returns_empty` | ✅ |
| AC4 | HN public Firebase API; no credentials | Firebase poll test + source inspection | ✅ |
| AC5 | Focused pytest exits 0 offline; User-Agent has tool name + `CONTACT_EMAIL` | `uv run pytest tests/discourse/test_reddit.py tests/discourse/test_hackernews.py` | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/discourse/test_reddit.py tests/discourse/test_hackernews.py -v  # 9 passed
uv run pytest                                                                    # 291 passed
uv run ruff check .                                                              # All checks passed
uv run ruff format --check .                                                     # 122 files already formatted
```

## Evidence files

- `ac1-registration.log`
- `ac2-oauth-defaults.log`
- `ac2-config-defaults.log`
- `ac3-missing-creds.log`
- `ac4-hn-firebase.log`
- `ac4-no-credentials.log`
- `ac5-user-agent.log`
- `ac-focused-pytest.log`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — discourse HTTP adapters / offline fixtures (no UI ACs).

## Notes for Reviewer

- Both adapters registered in `discourse/__init__.py`; `link_targets` stubbed `[]` (task 05).
- Reddit uses `SourceHttp` POST for OAuth + GET listings; skips with INFO log when `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` absent.
- HN polls `hacker-news.firebaseio.com/v0/newstories.json` + item JSON; no credential env vars.
- Hard invariants: discourse remains separate from scoring; adapters do not call LLMs or touch the DB.
