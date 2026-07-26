# Issue #2 QA report — v2

- Tested branch: `issue-2-bring-up-postgresql-and-grobid-via-docker-compose`
- Branch commit tested: `a7a4b8eb9cf9267b3169b021f43e105b836cc096`
- Tested at: `2026-07-26T13:06:52+07:00`
- Host architecture: Apple Silicon (`arm64`)
- Result: PASS

This rebuild addresses the Reviewer’s `[QA]` finding on the v1 report. The test removed
the existing containers while preserving the named PostgreSQL volume, started new
containers, recorded their initial `starting` state, polled the configured health checks,
and recorded the terminal `healthy` state. It did not rely on previously healthy
containers.

This issue has no UI or visual acceptance criteria. Screenshot capture was intentionally
omitted; service state, HTTP, SQL, architecture, and automated-test outputs are the
observable evidence.

The PostgreSQL bootstrap values were read from the prior issue-scoped container into the
local test process before that container was removed. They were neither printed nor
recorded in this report.

## Test plan

| Acceptance criterion | Observable check |
|---|---|
| AC1 | Remove the existing containers, run `docker compose up -d`, record immediate state, poll both configured health checks every five seconds, and record terminal `docker compose ps`. |
| AC2 | Request GROBID’s `/api/isalive` endpoint and require exit 0 plus body `true`. |
| AC3 | Run the task’s exact `psql "$DATABASE_URL" -c "select 1"` command and require one returned row. |
| AC4 | Inspect both image platforms and execute `uname -m` in both running containers; also inspect the clean-start output for emulation warnings. |
| AC5 | Run the task’s exact service configuration test command and require all tests to pass. |

## Acceptance criteria

### AC1 — Compose starts PostgreSQL and GROBID healthy

Commands:

```bash
docker compose down
docker compose up -d
docker compose ps

# Poll the containers' configured health checks every five seconds.
docker inspect "$(docker compose ps -q postgres)" --format '{{.State.Health.Status}}'
docker inspect "$(docker compose ps -q grobid)" --format '{{.State.Health.Status}}'

docker compose ps
```

Result: PASS. The named PostgreSQL volume was preserved, but both containers and the
Compose network were removed and recreated. The immediate state was truthfully recorded
as `starting`; both configured health checks reached `healthy` after 10 seconds, and the
terminal `docker compose ps` showed both services healthy.

Clean start:

```text
Container ai-researcher-postgres-1 Removed
Container ai-researcher-grobid-1 Removed
Network ai-researcher_default Removed
Network ai-researcher_default Created
Container ai-researcher-grobid-1 Created
Container ai-researcher-postgres-1 Created
Container ai-researcher-postgres-1 Started
Container ai-researcher-grobid-1 Started
```

Immediate state:

```text
NAME                       IMAGE                        SERVICE    STATUS
ai-researcher-grobid-1     lfoppiano/grobid:0.9.0-crf   grobid     Up Less than a second (health: starting)
ai-researcher-postgres-1   postgres:16                  postgres   Up Less than a second (health: starting)
```

Observed health transition:

```text
t=0s  postgres=starting grobid=starting
t=5s  postgres=healthy  grobid=starting
t=10s postgres=healthy  grobid=healthy
```

Terminal state:

```text
NAME                       IMAGE                        SERVICE    STATUS
ai-researcher-grobid-1     lfoppiano/grobid:0.9.0-crf   grobid     Up 10 seconds (healthy)
ai-researcher-postgres-1   postgres:16                  postgres   Up 10 seconds (healthy)
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

Result: PASS (exit 0). The clean `docker compose up -d` output contained no platform or
emulation warning.

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
3 passed in 0.00s
```

The test changes `DATABASE_URL` and `GROBID_URL` through `monkeypatch` and asserts that
`ai_researcher.config.get_settings()` returns those environment values. It also checks that
Compose requires the PostgreSQL password from the local environment.

## Repository completion gate

Command:

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Result: PASS (exit 0).

```text
6 passed in 0.64s
All checks passed!
6 files already formatted
```
