# Issue #2 QA report — v1

- Tested branch: `issue-2-bring-up-postgresql-and-grobid-via-docker-compose`
- Builder commit tested: `3cf7289a2338c3b6ff1e2ed90b09c95b17036477`
- Tested at: `2026-07-26T12:45:53+07:00`
- Host architecture: Apple Silicon (`arm64`)
- Result: PASS

This issue has no UI or visual acceptance criteria. Screenshot capture was intentionally
omitted; the service, HTTP, SQL, architecture, and automated-test outputs below are the
observable evidence.

The PostgreSQL password was recovered from the already-running issue-scoped container for
the local test session and was neither printed nor recorded in this report.

## Acceptance criteria

### AC1 — Compose starts PostgreSQL and GROBID healthy

Commands:

```bash
docker compose up -d
docker compose ps
```

Result: PASS (exit 0).

```text
Container ai-researcher-postgres-1 Running
Container ai-researcher-grobid-1 Running
NAME                       IMAGE                        SERVICE    STATUS
ai-researcher-grobid-1     lfoppiano/grobid:0.9.0-crf   grobid     Up 13 minutes (healthy)
ai-researcher-postgres-1   postgres:16                  postgres   Up 13 minutes (healthy)
```

### AC2 — GROBID liveness endpoint

Command:

```bash
curl -sf http://localhost:8070/api/isalive
```

Result: PASS (exit 0).

```text
true
```

### AC3 — PostgreSQL accepts `DATABASE_URL`

Command:

```bash
psql "$DATABASE_URL" -c "select 1"
```

Result: PASS (exit 0).

```text
 ?column?
----------
        1
(1 row)
```

### AC4 — Native Linux ARM64 images and runtimes

Commands:

```bash
uname -m
docker image inspect postgres:16 --format '{{.Os}}/{{.Architecture}}'
docker image inspect lfoppiano/grobid:0.9.0-crf --format '{{.Os}}/{{.Architecture}}'
docker compose exec -T postgres uname -m
docker compose exec -T grobid uname -m
```

Result: PASS (exit 0). `docker compose up -d` emitted no platform or emulation warning.

```text
host: arm64
postgres image: linux/arm64
grobid image: linux/arm64
postgres runtime: aarch64
grobid runtime: aarch64
```

### AC5 — Environment-driven service configuration

Command:

```bash
uv run pytest tests/test_services_config.py
```

Result: PASS (exit 0).

```text
collected 3 items
tests/test_services_config.py ...                                        [100%]
3 passed in 0.01s
```

The test suite changes `DATABASE_URL` and `GROBID_URL` through `monkeypatch` and asserts
that `ai_researcher.config.get_settings()` returns those environment values. It also checks
that Compose requires the PostgreSQL password from the local environment.

## Repository completion gate

Command:

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Result: PASS (exit 0).

```text
6 passed in 0.66s
All checks passed!
6 files already formatted
```
