# AC results — issue #71 QA v1

| AC | Criterion | Evidence | Result |
|----|-----------|----------|--------|
| AC1 | `docs/supersaiyan/designs/scirate-spike.md` exists with outcome, approach, recommendation | File present; `test_design_doc_records_spike_outcome`; records Cloudflare 403 + deferral | ✅ PASS |
| AC2 | `scirate` adapter implements `DiscourseSource`, registered, disabled by default (`DISCOURSE_SCIRATE_ENABLED`) | `test_scirate_implements_discourse_source_and_is_registered`; `test_discourse_scirate_enabled_defaults_false`; registered in `discourse/__init__.py` | ✅ PASS |
| AC3 | Flag unset ⇒ discourse sweep does not contact SciRate | `test_disabled_by_default_poll_makes_no_http_calls`; `test_discourse_sweep_does_not_contact_scirate_when_disabled` (tracking requester asserts zero HTTP) | ✅ PASS |
| AC4 | Successful fetch stores only scite count, arXiv ID, link — never page content | `test_enabled_fetch_stores_only_scite_count_arxiv_id_and_link`; `test_stored_row_shape_excludes_page_content` (`body`/`title`/`author`/`num_comments` all `None`) | ✅ PASS |
| AC5 | `uv run pytest tests/discourse/test_scirate.py` exits 0 (enabled + disabled) | 10 passed — see `pytest-ac.log` | ✅ PASS |

Hard invariants checked: discourse-only (no scoring import); no page content stored; disabled-by-default; silent 403 degrade.
