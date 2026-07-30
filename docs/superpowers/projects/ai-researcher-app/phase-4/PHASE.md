# Phase 4: Monitoring, Discourse & Temporal Digests

**Project:** ai-researcher-app
**Goal:** A daily sweep discovers new papers for subscribed topics and claims, re-runs ingestion and extraction on them, detects what changed, and produces a digest that reports evidence movement and community attention in two clearly separated channels.
**Depends on:** Phase 3

## Scope

This phase makes the system run on its own and answers "what changed since I last looked?"
at the claim level, not just the paper level.

1. **`DiscourseSource` interface and registry** — the community-attention counterpart to
   `EvidenceSource`, deliberately a separate protocol.
2. **Four discourse adapters** — Reddit, Hacker News, Google Research + Google Quantum AI
   blogs (RSS), and Hugging Face Papers / alphaXiv.
3. **Subscriptions** — track a topic (scope) or an individual claim.
4. **Scheduler** — APScheduler daily jobs that sweep evidence sources and discourse sources.
5. **Change detection** — new papers, new evidence for tracked claims, stance flips, and
   score movement.
6. **Temporal digests** — a readable report of what changed, with evidence and attention in
   separate sections.
7. **SciRate spike** — time-boxed investigation with an explicit defer exit.

## Out of Scope

Deferred or excluded:

- Any use of discourse data as a scoring input — this is a hard invariant, not a preference
- Sentiment scoring of community posts (attention volume and links only, no sentiment model)
- Figure and table grounding (post-v1)
- Push notifications, email, or Telegram delivery — digests are files and CLI output in v1
- Autonomous responses to what monitoring finds; the system reports, the human decides
- Web UI
- Vector embeddings of any kind

## Consumes from Prior Phase

From Phase 3:

- `claim` rows with stable IDs — subscription targets
- `claim_evidence` rows — new rows are the signal that evidence changed
- `claim_score` rows with `scored_at` — score movement over time
- `extraction.pipeline.extract_paper()` — run on newly discovered papers

From Phase 2:

- `trees/build.py` — new papers need trees before extraction
- `retrieval.traverse` — used to find evidence for tracked claims in new papers

From Phase 1:

- `sources/registry.py` — the registry pattern that `DiscourseSource` mirrors
- `ingest/pipeline.py` — reused for newly discovered papers
- `scope` rows — subscription targets at the topic level

## Produces for Next Phase

None — this is the final v1 phase.

## Architecture

**New package modules:**

```
src/ai_researcher/
  discourse/
    base.py             # DiscourseSource protocol — SEPARATE from EvidenceSource
    registry.py
    reddit.py
    hackernews.py
    rss_blogs.py        # Google Research, Google Quantum AI, and any RSS feed
    huggingface.py      # HF Papers / alphaXiv
    scirate.py          # spike only; ships disabled by default
  monitor/
    subscription.py     # topic- and claim-level subscriptions
    sweep.py            # evidence sweep: discover -> ingest -> tree -> extract
    discourse_sweep.py  # attention sweep, writes to its own tables
    changes.py          # change detection across runs
    scheduler.py        # APScheduler wiring
  digest/
    build.py            # assemble a digest for a time window
    render.py           # markdown output, two separated channels
```

**The separation invariant.** `DiscourseSource` is a distinct protocol writing to distinct
tables (`discourse_item`, `discourse_mention`). Nothing in `scoring/` may import from
`discourse/`, and no discourse value may be written to `claim_score`. This is enforced by an
import-boundary test, not by convention. The rationale is recorded in the design doc: SciRate
scites and Reddit upvotes measure attention, not validity, and conflating the two would
corrupt the evidence layer.

**`DiscourseSource` protocol:**

```python
class DiscourseSource(Protocol):
    name: str
    def poll(self, since: datetime) -> Iterable[DiscourseItem]: ...
    def link_targets(self, item: DiscourseItem) -> list[PaperRef]: ...
```

`link_targets` resolves a post to the papers it references (arXiv ID or DOI in the URL or
body). Items that reference no known paper are stored but unlinked — they are still signal
for a topic, just not for a claim.

**Sweep flow:**

```
daily
 ├─ evidence sweep    : for each subscribed scope -> discover new papers
 │                      -> ingest -> build tree -> extract -> link evidence -> rescore
 └─ discourse sweep   : for each enabled DiscourseSource -> poll since last run
                        -> resolve link_targets -> store mentions
                                    │
                              change detection
                                    │
                                 digest
```

**Change detection** compares the current state against the last completed sweep:
new papers in scope; new `claim_evidence` rows for subscribed claims; stance flips (a claim
that gained a `refutes` link); `claim_score` movement beyond a threshold; and new
`discourse_mention` rows for papers backing subscribed claims.

**SciRate spike (time-boxed).** One task, capped at one working session. It attempts a
polite, signal-only fetch: scite count keyed by arXiv ID, identifying User-Agent, low rate,
cached, never storing page content and never used for training — consistent with the site's
`use=reference` and `ai-train=no` signals. Cloudflare returns 403 to non-browser clients, so
if a compliant fetch does not work within the time box, the adapter ships **disabled by
default** with its findings recorded in `docs/supersaiyan/designs/scirate-spike.md` and the
work moves to future work. It must never block the phase.

## Requirements

1. A migration adds `discourse_source(id, name, kind, enabled, last_polled_at)`.
2. A migration adds `discourse_item(id, source_id, external_id, url, title, author,
   posted_at, score, num_comments, retrieved_at)` with uniqueness on
   `(source_id, external_id)`.
3. A migration adds `discourse_mention(id, discourse_item_id, paper_id, resolved_by,
   created_at)` where `resolved_by` records whether the link came from an arXiv ID or DOI.
4. A migration adds `subscription(id, kind, scope_id, claim_id, created_at, active)` where
   `kind` is `topic` or `claim`, with exactly one of `scope_id`/`claim_id` non-null.
5. A migration adds `sweep_run(id, kind, started_at, finished_at, state, items_found, error)`
   where `kind` is `evidence` or `discourse`.
6. `DiscourseSource` is defined in `discourse/base.py` as a protocol distinct from
   `EvidenceSource`; a test asserts the two protocols share no base class.
7. `scoring/` imports nothing from `discourse/` — a complete, decidable import-boundary
   test (checks the exact `ai_researcher.discourse` package path, not a loose substring).
   No discourse-derived value is ever written to `claim_score`, enforced in three layers:
   an AST scan for direct calls to `save_quality`/`save_confidence` from a discourse-importing
   file (best-effort — it does not trace calls through `score_scope_confidence` or an
   injected `score_fn`-style callable, the same kind of indirection that made Phase 3's AC4
   gate an unbounded chase); a structural check that `ConfidenceClaim`/`QualityClaim`/
   `QualityEvidence` (the fixed, enumerable set of fields either scoring function can ever
   read) carry no discourse-flavored field, which is complete because a frozen dataclass's
   fields can't be extended without changing its visible declaration; and a narrow check
   that the one function loading those dataclasses from the database never references a
   discourse table. The first layer is defense-in-depth; the second and third are the actual
   guarantee for indirect callers.
8. Reddit, Hacker News, RSS blogs, and Hugging Face/alphaXiv adapters each implement the
   protocol, are registered, and are unit-tested offline against recorded fixtures.
9. The RSS adapter is configuration-driven: adding a feed means adding a URL to config, not
   writing code. Google Research and Google Quantum AI ship as default feeds.
10. Every discourse adapter honors the source's rate limits and sends a descriptive
    User-Agent with a contact address, read from config.
11. Reddit access uses the official API with OAuth credentials from environment variables;
    when credentials are absent the adapter is skipped with a clear log line, not an error.
12. `link_targets` resolves arXiv IDs and DOIs from item URLs and body text; unresolvable
    items are stored with no `discourse_mention` row rather than dropped.
13. `airesearch subscribe topic <scope>` and `airesearch subscribe claim <claim-id>` create
    subscriptions; `airesearch subscriptions` lists them; `airesearch unsubscribe <id>`
    deactivates without deleting history.
14. `airesearch sweep --kind evidence` discovers new papers for subscribed scopes and runs
    ingest → tree → extract → evidence-link → rescore on each, writing a `sweep_run` row.
15. `airesearch sweep --kind discourse` polls every enabled discourse source since its
    `last_polled_at`, stores items and mentions, and writes a `sweep_run` row.
16. Sweeps are resumable and idempotent: a repeat run with no new upstream content creates
    zero new papers and zero duplicate `discourse_item` rows.
17. Sweeps honor the 1,000-paper scope ceiling from Phase 1 and stop adding papers to a scope
    at the ceiling with a clear log line.
18. Change detection reports: new papers per scope; new `claim_evidence` per subscribed
    claim; stance flips; `claim_score` movement beyond a configurable threshold (default 10
    points); and new `discourse_mention` rows for papers backing subscribed claims.
19. `airesearch digest --since <date>` renders a markdown digest to
    `docs/supersaiyan/runs/digest-<date>.md` and to stdout.
20. The digest has two clearly labelled top-level sections — "Evidence" and "Community
    attention" — and never presents an attention number as evidence of validity. A test
    asserts both section headers are present and that no attention figure appears inside the
    evidence section.
21. Score movement in the digest shows `confidence` and `evidence_quality` as separate
    before/after pairs, never a blended delta.
22. APScheduler runs the evidence sweep and the discourse sweep on a daily schedule;
    `airesearch schedule start` runs it in the foreground and `airesearch schedule status`
    reports the next run time per job.
23. A failing discourse source does not abort a sweep: the error is recorded on the
    `sweep_run` row and the remaining sources continue.
24. The SciRate adapter ships **disabled by default**. Enabling it requires an explicit
    config flag. Its findings — whether a compliant fetch is achievable — are written to
    `docs/supersaiyan/designs/scirate-spike.md` regardless of outcome.
25. No source content from any scraped discourse source is used to train or fine-tune a
    model, and the digest links back to the original post rather than reproducing it in full.

## Acceptance

- `uv run pytest` exits 0, including the import-boundary tests proving `scoring/` does not
  import `discourse/` and that `DiscourseSource` and `EvidenceSource` are distinct protocols.
- `uv run airesearch subscribe topic surface-codes` then `uv run airesearch subscriptions`
  lists the subscription as active.
- `uv run airesearch sweep --kind discourse` completes, writes a `sweep_run` row with state
  `completed`, and stores `discourse_item` rows; re-running immediately adds zero duplicates.
- `uv run airesearch sweep --kind evidence` discovers and fully processes at least one new
  paper end-to-end (ingested, tree built, claims extracted) when upstream has new content.
- Disabling network access for one discourse source and re-running the sweep shows that
  source recorded as failed on `sweep_run` while the others complete.
- `uv run airesearch digest --since 2026-08-01` writes a markdown file containing both an
  "Evidence" and a "Community attention" section, with score movement shown as separate
  confidence and evidence-quality pairs.
- A SQL query confirms no row in `claim_score` traces to a discourse source.
- `uv run airesearch schedule status` reports a next-run time for both the evidence and
  discourse jobs.
- `docs/supersaiyan/designs/scirate-spike.md` exists and records the outcome, and the SciRate
  adapter is disabled unless explicitly enabled in config.

## Source

- Project: docs/superpowers/projects/ai-researcher-app/PROJECT.md
- Phase spec date: 2026-07-26
