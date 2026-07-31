# AGENTS.md — AI-Researcher

Read this first. It applies to **every** agent working in this repo — Codex, Cursor, Claude
Code, or any other. Tool-specific additions live in `CLAUDE.md` and `.cursor/rules/`, but
nothing there may contradict this file.

## What this project is

A local-first research engine for quantum computing and AI literature, for a single
researcher. It narrows a broad topic to a defensible corpus, ingests and structurally parses
papers, and answers questions where **every statement cites a specific paper section with a
page range**.

Full context: [docs/superpowers/projects/ai-researcher-app/PROJECT.md](docs/superpowers/projects/ai-researcher-app/PROJECT.md)

## How work is dispatched

Work is defined by **task files**, not by conversation. Each task file is a complete
contract — goal, acceptance criteria, exact file paths, exact test commands.

```
docs/superpowers/projects/ai-researcher-app/
  PROJECT.md                    # cross-phase architecture and constraints
  phase-N/PHASE.md              # what phase N builds, its requirements and acceptance
  phase-N/NN-task-name.md       # one task = one PR
```

**Before starting any task:** read its task file, then `PHASE.md` for that phase, then
`PROJECT.md`. Do not begin from a chat description alone.

**Task order is a strict chain.** Each task's `depends_on_task` frontmatter names its
predecessor. Do not start a task whose predecessor has not merged.

**A task is done when its acceptance criteria pass** — every one of them, verified by
running the stated command, not by inspection.

## Phase ownership

| Phase | Tool | Loop |
|-------|------|------|
| 1 — Foundation & Corpus Ingestion | Codex | manual |
| 2 — Vectorless Tree Retrieval & Grounded Q&A | Codex | manual |
| 3 — Structured Extraction & Dual Scoring | Cursor | manual |
| 4 — Monitoring, Discourse & Temporal Digests | Cursor | manual |

Phases run manually by default: pick up the issue, build it, verify acceptance criteria,
open a PR, move the board card yourself.

Each tool has its own board config, so starting one never touches another's settings:

| Config | `worker_backend` | Script | Auth |
|--------|------------------|--------|------|
| `ai-researcher-codex.json` | `codex-exec` | [`scripts/supersaiyan-codex-run.sh`](scripts/supersaiyan-codex-run.sh) | Codex CLI subscription |
| `ai-researcher-cursor.json` | `cursor-agent` | [`scripts/supersaiyan-cursor-run.sh`](scripts/supersaiyan-cursor-run.sh) | Cursor subscription (`agent login`) |
| `ai-researcher-claude.json` | `workflow` | Claude Code `/supersaiyan run ai-researcher-claude` | Claude subscription |

Always pass the config slug explicitly to whichever script you're using (e.g.
`scripts/supersaiyan-codex-run.sh ai-researcher-codex`) — never rely on
`.claude/supersaiyan/active` for dispatch, since that pointer is a single shared value and
whichever tool set it last wins for anyone who omits the slug.

**One backend at a time regardless of config file.** All three configs point at the same
GitHub Project (#6), so two dispatchers running together still race on issue-assignee
claims and produce duplicate PRs — the per-tool orphan guards in each script refuse to
start if another tool's runner process is already alive, but that only helps if you don't
run them in separate terminals faster than the guard can catch it.

Docs: [`docs/supersaiyan/cursor-runner.md`](docs/supersaiyan/cursor-runner.md),
[`docs/supersaiyan/codex-runner.md`](docs/supersaiyan/codex-runner.md).

Board: https://github.com/users/BankNatchapol/projects/6

## Hard invariants

These are not preferences. Each is enforced by a test that fails the build. If a change
requires breaking one, stop and raise it rather than working around the test.

1. **Retrieval is vectorless.** No embeddings, no vector similarity, no pgvector, no
   reranker models. Retrieval is LLM reasoning over document trees built from GROBID's TEI
   section hierarchy. `pgvector` is a recorded escape hatch, not a component.
2. **Every stored assertion carries a passage anchor** — paper ID, tree node ID, section
   path, page range, extraction model and version. Bare claim text is never stored. Database
   `NOT NULL` constraints enforce this.
3. **Confidence and evidence quality are two separate scores.** Never averaged, multiplied,
   blended, or surfaced as one number under any name. `confidence` describes the pipeline;
   `evidence_quality` describes the science.
4. **Evidence and discourse are separate channels.** Nothing from a `DiscourseSource`
   (Reddit, Hacker News, blogs, SciRate) may influence any score. `scoring/` must not import
   from `discourse/`. Community attention measures interest, not validity.
5. **All model calls go through `ai_researcher.llm.gateway`.** No other module imports
   a model CLI or imports an LLM SDK. Access is via CLI subscription (`claude -p`,
   `codex exec`, `agent -p --mode ask`) — there is no provider API key. Backend is resolved
   per job from config. Calls are non-agentic (read-only, turn-limited) and callers batch
   many items per call. The `cursor` backend has no CLI-level schema enforcement (`agent`
   has no `--json-schema`/`--output-schema` equivalent) — structured-output jobs routed to
   it rely on prompt-embedded instructions alone and are best-effort, not a guaranteed-valid
   substitute for `claude`/`codex`.
6. **Sources are plugins.** Adding a source means writing one adapter against a fixed
   protocol and registering it — never editing the pipeline. `EvidenceSource` and
   `DiscourseSource` are deliberately distinct protocols sharing no base class.
7. **One store.** PostgreSQL, plain. No Neo4j, no DuckDB, no second database.
8. **Corpus ceiling is 1,000 papers per scope.** Precision over recall — the system narrows
   scope rather than maximizing candidates.

## Stack

- **Python 3.11+** — floor set by paper-qa and the MCP SDK
- **uv** for dependencies and Python version pinning — not Poetry, not bare pip
- **pytest** for tests, **ruff** for lint and format — not black, not flake8
- **PostgreSQL** (plain) as the only store
- **GROBID** in Docker for PDF → TEI parsing
- **CLI model gateway** — shells out to `claude -p`, `codex exec`, or `agent -p --mode ask`
  per job type. No API keys.
- Two surfaces over one core library: a **CLI** (`airesearch`) and an **MCP server**. Neither
  contains business logic; both call the same core functions.

## Commands

```bash
uv sync                        # install
uv run pytest                  # all tests
uv run ruff check .            # lint
uv run ruff format --check .   # format check
docker compose up -d           # Postgres + GROBID
uv run airesearch --help       # CLI
```

Run `uv run pytest && uv run ruff check .` before opening any PR. A task is not complete
until both pass.

## Editing shared config files

`.gitignore`, `.env.example`, `pyproject.toml`, `docker-compose.yml`, `AGENTS.md`, and
`CLAUDE.md` are **append-or-merge only**. Read the file, add your lines, keep everything
already there.

Never rewrite one of these from scratch, even when a task says "create entries for X". A
task listing three `.gitignore` entries means *add* those three — not replace the file with
only those three. Deleting an existing rule is a silent regression that surfaces commits
later, not now.

If your change makes a file surface something previously ignored or excluded, that is a
signal you removed a rule — go back and check before reporting the task complete.

## Conventions

- **Adapters never touch the database and never call an LLM.** They return plain dataclasses,
  which is what makes them testable against recorded fixtures with no network.
- **Tests run offline.** Adapter and pipeline tests use committed fixtures. Tests needing a
  live service are marked and skipped when the service is unreachable.
- **Failures are recorded, not raised.** A single paper failing to parse, extract, or download
  is logged against that paper; the run continues.
- **Everything is resumable.** Re-running ingest, index, extract, or sweep with no new input
  does zero work and exits 0.
- **Secrets come from environment variables or a gitignored `.env`.** Never committed.
  `.env.example` documents every required variable.

## Out of scope for v1

Do not build these, even if they seem natural: autonomous paper writing or hypothesis
generation, peer-review or critique generation, multi-user or auth, a web UI, PubMed and
biomedical sources, figure and table grounding, fully-local inference, and any vector
embedding.
