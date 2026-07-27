# Issue #26 QA evidence — v1

- PR: #34
- Branch: `issue-26-add-tree-node-retrieval-trace-schema`
- Tested commit: `dd6e21e6ad7fc51afe796c0c25864fee33fac6f6`
- Result: PASS
- Evidence type: database, CLI, and automated-test output
- Visual evidence: intentionally omitted because this issue has no UI or visual acceptance criteria

## Acceptance test plan and results

### AC1 — migration applies once and is idempotent

Observable check: create a fresh PostgreSQL database, invoke the production CLI twice, and
inspect both exit codes and messages.

```text
$ uv run airesearch db migrate
Applied migration 0001_initial.
Applied migration 0002_paper_parse_error.
Applied migration 0003_trees.

$ uv run airesearch db migrate
Database already up to date.
```

Both invocations exited 0.

### AC2 — `tree_node` has the required columns

Observable check: query `information_schema.columns` after applying migrations.

```text
tree_node | {id,paper_id,section_id,parent_id,node_path,title,summary,page_start,page_end,depth,tree_schema_version,summary_model,created_at}
```

The observed set and ordinal order contain all 13 required columns.

### AC3 — `retrieval_trace` has the required columns

Observable check: query `information_schema.columns` after applying migrations.

```text
retrieval_trace | {id,question,scope_id,expanded_node_ids,selected_node_ids,nodes_expanded,stopped_reason,created_at}
```

The observed set and ordinal order contain all 8 required columns.

### AC4 — paper and section links are non-null foreign keys

Observable check: join `information_schema.columns`, `key_column_usage`,
`referential_constraints`, and `constraint_column_usage`.

```text
tree_node | paper_id   | is_nullable=NO | references paper(id)
tree_node | section_id | is_nullable=NO | references section(id)
```

### AC5 — null `section_id` is rejected by PostgreSQL

Observable checks:

```text
NOTICE: null section_id rejected as expected
```

The exact task command also passed:

```text
$ uv run pytest tests/test_tree_schema.py
collected 2 items
tests/test_tree_schema.py .. [100%]
2 passed
```

## Repository verification

Exact command:

```bash
uv run pytest tests/test_tree_schema.py && uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Results:

```text
tests/test_tree_schema.py: 2 passed
full suite: 98 passed
ruff check: All checks passed!
ruff format --check: 58 files already formatted
```
