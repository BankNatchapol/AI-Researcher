# SuperSaiyan plugin issues found while dogfooding on AI-Researcher

These are problems in **SuperSaiyan itself** (the plugin/dispatcher, not this project's
code), found by actually running it across three tools — Claude Code, Codex, Cursor — on a
real multi-phase project. Each entry states what happened, the evidence, current status, and
what to fix upstream. Ordered roughly chronologically, starting from the first blocked-card
incident.

---

## 1. Shared mutable `worker_backend` caused a cross-tool collision

**What happened:** `worker_backend` lived in one shared config file
(`.claude/supersaiyan/configs/ai-researcher.json`), read by all three dispatchers. Starting
the Cursor dispatcher flipped it to `cursor-agent`; the next Codex run then refused to start
because the field no longer said `codex-exec`.

**Status: fixed in this project**, not upstream in the plugin. Worked around by giving each
tool its own config file (`ai-researcher-codex.json`, `ai-researcher-cursor.json`,
`ai-researcher-claude.json`), all pointing at the same GitHub Project but sharing no mutable
field. Commit message from the fix:

> "worker_backend was a single mutable field in one shared config file, read by all three
> dispatchers. Two tools writing to it caused a real incident: the Codex run refused to
> start because a parallel Cursor setup had flipped it to cursor-agent."

**Upstream fix needed:** `references/setup.md` / `references/onboard.md` should generate one
config per intended tool from the start when a project plans to use more than one, rather
than a single `worker_backend` field a human has to remember to isolate after getting burned
once.

---

## 2. Issue #8 / PR #22 — the rebuild-cap block and the review-thread loop

**What happened:** A single Phase 1 task (`Implement PDF acquisition with open-access
detection`) went through an unusually long cycle:

```
Build → QA v1 → Review rebuild 1 → Build → QA v2 → Review rebuild 2 → Build → QA v3
  → Review BLOCKED (rebuild_cap=2 reached, human authorization required)
  → human-authorized fix → QA v4
  → Review Gate 1 bounce (unresolved GitHub review thread, not a code defect)
  → Build (Gate 1 resolve) → QA v5 → Review ✅ Merged
```

Two distinct friction points, both real, both worth separating:

**2a. Rebuild-cap block (working as designed, but costly).** After two automated rebuild
attempts both left an `IncompleteRead`/`HTTPException` handling gap in the download path,
the Reviewer correctly refused to authorize a third automatic attempt and blocked the card:

> "Why blocked: AC4 is still violated by truncated HTTP responses, and the configured
> rebuild cap of 2 has been reached. ... Why I (bot) cannot decide: Overriding
> `rebuild_cap=2` would bypass the board safety policy after two automated rebuilds."

This is the safety mechanism working correctly — but the underlying defect (a narrow
exception-type gap) took three attempts to actually fix, which is a real cost of the
adversarial-QA design (mutation-testing-style probes keep finding edge cases the previous
fix didn't cover).

**2b. Review Gate 1 bounce for an already-correct fix.** After the human-authorized fix
passed QA v4, Review bounced the card again — not because the code was wrong, but because a
GitHub PR review **thread** the Reviewer itself had created was still marked unresolved:

> "Reason: the fixed `IncompleteRead` defect still has an unresolved `[builder]` review
> thread. ... Review/tests: not entered; Gate 1 requires all threads resolved first."

This cost an entire extra Build→QA cycle (`Gate 1 resolve`, QA v5) purely to click "resolve"
on a thread whose underlying finding was already fixed and verified.

**Status: 2a is working as designed** (the cost is inherent to strict rebuild caps, not a
bug). **2b is unresolved** — flagged in `docs/supersaiyan/cursor-runner.md` as a known
caution ("unstick any thrashing card (e.g. issue #8 / PR #22 review-thread loops)") but never
fixed at the skill level.

**Upstream fix needed:** `super-review`'s Gate 1 check should auto-resolve a thread it
created once its own re-verification confirms the finding is fixed, instead of requiring a
separate Builder pass whose only job is marking the thread resolved. Alternatively, Gate 1
should distinguish "unresolved thread, unverified fix" from "unresolved thread, fix already
reverified" and only bounce on the former.

---

## 3. Builders self-blocked on unmerged predecessors before `strict_task_chain` existed

**What happened:** Early runs (before `strict_task_chain` was added to the dispatch policy)
dispatched Builder workers onto multiple Ready issues in parallel without checking whether
each issue's predecessor had actually merged. The workers themselves caught the violation via
`AGENTS.md`'s task-order rule and self-blocked rather than building out of order — e.g.:

> "Card: #3 Add the migration runner and core database schema — Why blocked: Required
> predecessor issue #2 is still open and Blocked, so task 02 has not merged into `main`."

This happened on four consecutive issues (#2, #3, #4, #5), each blocking on the previous
one, before the chain untangled — real dispatch cycles spent on cards that could never have
succeeded.

**Status: fixed in this project.** `strict_serial_ready_issue()` in
`scripts/supersaiyan-dispatch-policy.sh` now gates Build-lane card selection to the
lowest-numbered non-terminal issue, so a successor is never even offered to a Builder until
its predecessor reaches Done or Skipped. Covered by tests
(`test_successor_waits_while_predecessor_is_in_qa`, etc.) in
`tests/test_supersaiyan_dispatch_policy.py`.

**Upstream fix needed:** this dependency-chain awareness (`depends_on_task` /
`depends_on_phase` frontmatter → dispatch order) doesn't exist in upstream SuperSaiyan at
all — every project that uses `depends_on_task` chains and multi-worker dispatch will hit
this exact problem until `strict_task_chain` (or equivalent) ships in the plugin itself,
not just as a per-project workaround script.

---

## 4. A Builder overwrote `.gitignore` from scratch instead of appending

**What happened:** During the very first Codex smoke test (issue #1, pure scaffolding), the
worker created a fresh `.gitignore` containing only the three lines it thought were relevant,
silently deleting pre-existing rules (`.claude/supersaiyan/active`, the Codex worker log
directory, `.worktrees/`). Caught by manual review before merge, not by any automated check.

**Status: fixed in this project**, not upstream. `AGENTS.md` gained an explicit
"Editing shared config files" section requiring append-or-merge for `.gitignore`,
`.env.example`, `pyproject.toml`, `docker-compose.yml`, `AGENTS.md`, and `CLAUDE.md` itself.
Verified fixed: a later PR (#14 → rebuilt as PR that landed) diffed `.gitignore` as
`6+ 0-` — pure addition, nothing deleted.

**Upstream fix needed:** this is a generic enough failure mode (agents rewriting a config
file "for the task" instead of extending it) that it belongs in SuperSaiyan's own
`super-build` skill instructions by default, not something every project has to discover and
patch into its own `AGENTS.md` independently.

---

## 5. GROBID page-range extraction only read the first coordinate group

**What happened:** Found during Phase 1 review — GROBID's `coords` attribute is
semicolon-separated `page,x,y,w,h` groups (one per line-box), but the original
`_page_from_coords` implementation only read the first group, understating `page_end` for
any paragraph spanning a page break.

**Status: fixed in this project.** Recorded as PROJECT.md risk #9 with an explicit
"fix before Phase 2 ships" gate (since Phase 2's citation rendering depends directly on
correct page ranges). Verified fixed: `_pages_from_coords` (renamed, plural) now parses
every group and takes true min/max, with a dedicated test
(`test_tei_page_range_uses_every_coordinate_group_in_a_paragraph`).

**Not a SuperSaiyan/dispatcher issue** — this is domain code, included here only because it
was a real defect the review process caught before it shipped, which is itself evidence the
review gate does its job when the finding is a code defect rather than a thread-resolution
technicality (contrast with #2b above).

---

## 6. Fixed-tick polling drained the GitHub GraphQL quota to zero

**What happened:** The original dispatcher design polled the board on a fixed timer
(`tick_seconds`, originally much shorter than 600) regardless of whether anything was
happening. During a real Phase 1 Codex run this **actually exhausted the GraphQL quota to
0**, twice, each forcing a ~20–30 minute enforced sleep:

```
[12:04:43] ⚠ GraphQL rate limit low (49 left) — sleeping 1845s until reset
[12:11:59] ⚠ GraphQL rate limit low (0 left) — sleeping 1409s until reset
```

**Status: fixed in this project**, not upstream, in two layers:

- **Layer 1 (immediate fix, still upstream-worthy on its own):** bump `tick_seconds` to 600,
  and forbid lane workers from independently polling the board (`gh project item-list` /
  `field-list` / `view`) — workers were previously scanning the board themselves on top of
  the dispatcher's own polling, multiplying the problem. This is now enforced by
  `test_runners_poll_locally_while_busy_and_forbid_worker_board_scans`.
- **Layer 2 (structural fix, this session):** replaced the fixed tick entirely with
  event-driven dispatch. While any lane is busy, the dispatcher only checks local process
  liveness (`kill -0`) — zero GitHub calls — and fetches the board the instant a worker
  exits, instead of waiting out a fixed interval. A board recheck happens only when every
  lane is idle and nothing was dispatchable (`idle_recheck_seconds`, default 60s).

**Measured, not just claimed:** on a live Cursor run against this project's Phase 3 (issue
#43), the build worker exited at `22:06:06` and QA dispatched at `22:06:12` — a **6 second**
reaction, versus up to 600 seconds (10 minutes) under the old fixed-tick design for the same
transition observed earlier on issue #42 (`21:03:27` build → `21:13:30` QA → `21:23:40`
review, each transition landing almost exactly 10 minutes apart).

**Upstream fix needed:** this is the single highest-value fix to push into SuperSaiyan
itself. Every project using the fixed-tick dispatcher inherits both the slowness (up to one
full tick of dead time per pipeline stage transition) and the latent rate-limit risk (any
sustained idle period at a short tick setting can reproduce the original incident) that this
project had to work around locally. The event-driven replacement
(`scripts/supersaiyan-codex-run.sh`, `scripts/supersaiyan-cursor-run.sh` in this repo) is a
directly portable reference implementation.

---

## 7. Codex and Cursor integration required forking the dispatcher, not configuring it

**What happened:** `supersaiyan run` is not a set of instructions — it's an executor.
Upstream's dispatcher hardcodes `claude -p` as the worker spawn call. Getting Codex and
Cursor working required forking the whole runner script per tool, not just changing a
config value:

- `scripts/supersaiyan-codex-run.sh` — spawns `codex exec` instead of `claude -p`
- `scripts/supersaiyan-cursor-run.sh` — spawns `agent -p` instead of `claude -p`
- Both needed lane prompts rewritten to point at absolute skill paths
  (`$CODEX_SKILLS_DIR` / `$CURSOR_SKILLS_DIR`) since neither CLI auto-loads Claude Code
  plugin skills the way `claude -p` does
- Both needed an explicit prompt override telling the worker **not** to follow the
  `super-build`/`super-qa`/`super-review` skill text where it describes spawning its own
  `claude -p`/`codex exec` sub-worker — those skills were written assuming a Claude Code
  parent process
- Skills had to be manually symlinked into `~/.codex/skills` and `~/.cursor/skills`
  (`scripts/setup-cursor-skills.sh`) since neither tool sees the Claude plugin cache
- Auth models differ and needed different guards: Codex authenticates via its own CLI
  session; Cursor requires subscription login (`agent login`) with an explicit runtime
  warning if `CURSOR_API_KEY` is set, since that's a CI escape hatch, not the intended path
- Sandbox settings needed real-world tuning per tool: Codex's `workspace-write` sandbox is
  documented to sometimes silently ignore `network_access=true` on macOS
  ([openai/codex#10390](https://github.com/openai/codex/issues/10390)), requiring
  `danger-full-access` for `git push`/`gh` to work reliably; Cursor needed the equivalent
  `--sandbox disabled`

**Status: working, verified end to end for both.** Codex drained all 11 Phase 1 issues and
8 Phase 2 issues for real. Cursor drained issue #42 (Phase 3) for real — genuine PR, genuine
merge, genuine truth-gate score (94/100), independently re-verified afterward rather than
trusted from the worker's own summary.

**Upstream fix needed:** SuperSaiyan should define a small `Backend` interface (spawn
command, skills-dir resolution, sandbox flag name, auth check) that `dispatch_lane()` calls
through, so adding a new CLI tool is implementing one interface rather than forking and
maintaining a ~650-line script per tool. Right now the Codex and Cursor runners are
near-identical copies that have to be kept manually in sync (as this session had to do
for the event-driven dispatch change in #6 — the same edit was applied twice, by hand).

---

## 8. The Cursor orphan-guard pattern never matched a real worker process

**What happened:** every place that needed to detect a live Cursor worker —
`supersaiyan-cursor-run.sh`'s own orphan guard, its `pkill` stop instructions, the
dashboard's worker count, and `docs/supersaiyan/cursor-runner.md`'s stop command — used the
pattern `agent -p .*lane worker for SuperSaiyan`, assuming `agent` and `-p` sit adjacent on
the command line. They don't. The real `agent` CLI re-execs itself as:

```
agent --use-system-ca /Users/x/.local/share/cursor-agent/versions/<ver>/index.js -p --force ...
```

`-p` is separated from `agent` by `--use-system-ca` and the `index.js` path, so the pattern
never matched a real worker — `pgrep -f 'agent -p .*lane worker for SuperSaiyan'` returned 0
every time, live, on this project's real run:

```
$ pgrep -f 'agent -p .*lane worker for SuperSaiyan' | wc -l
0
$ pgrep -f 'agent.*lane worker for SuperSaiyan' | wc -l
1
```

Practical consequences, all silent: the dispatcher's own orphan guard could never detect a
second Cursor dispatcher's live workers (only the dispatcher *process* name was actually
checked); the documented `pkill -f 'agent -p .*lane worker...'` stop command would not kill
a running worker; the dashboard's Cursor worker count always showed 0 regardless of actual
activity — which is what looked like "nothing is running" from the outside while a worker
was, in fact, genuinely alive and working.

**Status: fixed in this project.** Pattern corrected to `agent.*lane worker for
SuperSaiyan` (drops the false adjacency assumption) in
`scripts/supersaiyan-cursor-run.sh`, `scripts/watch-run.sh`, and
`docs/supersaiyan/cursor-runner.md`. Regression test added
(`test_orphan_pattern_matches_the_real_cursor_agent_command_line`) that checks the fixed
pattern against a real captured command-line shape and asserts the broken pattern doesn't
appear anywhere in the fixed files.

**Upstream fix needed:** any SuperSaiyan tool integration that shells out to a CLI wrapping
another process (as `agent` does) needs its orphan/liveness patterns verified against the
*actual* live command line, not assumed from the documented invocation syntax. This class of
bug is easy to introduce and silent to ship — nothing errors, the guard just quietly never
fires.

---

## 9. `rebuild_cap`'s counter never resets after human authorization, and appears to ignore root-cause-hash matching

**What happened:** Issue #46 hit `rebuild_cap` (2) and blocked. A human read the finding,
confirmed it was real, and authorized a rebuild by dragging the card back to Ready. The
rebuild produced a **different, unrelated defect** — verified by direct code comparison,
not assumed — yet the Reviewer blocked again citing the same "rebuild cap exhausted"
reasoning, and the dashboard still showed `attempt 3/3`.

The plugin's own reference doc (`references/run.md`) states the cap gate is keyed on
repetition:

> "Two consecutive failures on the same card with **identical hash** AND **same lane**
> count as the same root cause. Hits `rebuild_cap` → Blocked."

But the two actual blocks on this issue carried **different** `root-cause-hash` values
(`e62d665b7fee` for the first defect, `c5067e033f1e` for the second, confirmed genuinely
distinct by reading the code both times) — yet both triggered the same cap-exhaustion
block. Either the cap is really a raw cumulative attempt ceiling regardless of hash, and the
"identical hash" language describes something else (perhaps just root-cause grouping for
messaging purposes), or the Reviewer isn't following its own documented nuance.

Separately: **nothing in the plugin resets or removes the `loop:rebuild-N` label after a
human authorizes continuing past the cap.** The label is a plain monotonic counter,
incremented on every rebuild bounce, permanent for the issue's lifetime. This means every
subsequent failure on the same card — even a brand-new, unrelated third defect — is likely
to immediately re-trigger the cap block and require another human authorization comment,
regardless of how many genuinely different bugs get found and fixed along the way.

**Status: fixed in the plugin itself** (commits `0228880`, `5fc09c7` in
`BankNatchapol/SuperSaiyan`, local only — not yet pushed as of this writing). Two changes:

1. **Enforced the hash-aware reset the doc already claimed to have.** The rule ("different
   hash resets the counter") existed in prose but wasn't being applied at the actual decision
   point. Moved it inline into the halt-gates table and the Reviewer's step-7 decision list as
   an explicit comparison step. **Verified working, live, on the same project:** issue #47
   went through 4 rebuilds — verbatim-overlap ordering, cross-paper replication leak, unwired
   repeated-extraction data, stale confidence refresh — four genuinely distinct defects, and
   the Reviewer's own comments now show an explicit "Cap audit: prior hash X; current hash Y
   differs, so this is progress" line before routing each one onward instead of blocking.

2. **Added `config.absolute_rebuild_ceiling` (default 4) as a second, independent gate.**
   Fixing (1) alone removed the *only* ceiling that existed — a card producing genuinely
   different failures could now rebuild unattended forever, with no human checkpoint ever
   forced, burning real subscription-backed model calls indefinitely. This surfaced as a
   direct user concern after watching #47 sail through 4 rebuilds: the hash-aware fix was
   correct, but it traded a guaranteed (if occasionally over-eager) ceiling for no ceiling at
   all. The new gate checks a hard total regardless of hash, restoring the bounded-attempts
   guarantee while keeping the false-positive fix.

**Also found while fixing this:** `run.md` and `config-schema.json` each exist in **two
copies** in the plugin — under `skills/super-board/references/` (read by the Codex/Cursor
external dispatcher forks) and `skills/supersaiyan/references/` (read by Claude Code's native
`/supersaiyan run`). The first hash-aware patch was only applied to the `super-board` copy
initially; the `supersaiyan` copy silently had neither fix until this was caught and both
copies were patched identically. Any future change to lane-lifecycle behavior needs to touch
both, or the two dispatch paths will quietly diverge.

---

## 10. `run.md` and `config-schema.json` each exist as two silently-divergent copies

**What happened:** while fixing item #9, the hash-aware rebuild-cap patch was first applied
only to `skills/super-board/references/run.md` — the copy read by the Codex and Cursor
external dispatcher forks (`scripts/supersaiyan-codex-run.sh`, `scripts/supersaiyan-cursor-run.sh`
in this project, via `~/.codex/skills/super-board/...` and `~/.cursor/skills/super-board/...`
symlinks). It took a second pass to notice `skills/supersaiyan/references/run.md` — the copy
read by Claude Code's own native `/supersaiyan run` — is a **separate, independently
maintained file** with the same content minus a `docs/super-board/` → `docs/supersaiyan/`
path rewrite. It had received neither this fix nor any prior one.

**Status: fixed for this specific change** — both copies now carry the hash-aware reset and
the `absolute_rebuild_ceiling` gate identically. The structural risk remains: nothing enforces
these two copies staying in sync, and the divergence is invisible until someone happens to
compare them (as happened here only by accident, while re-reading files for an unrelated fix).

**Upstream fix needed:** either make one copy the real source and have the other reference/
import it, or add a CI check that diffs the two (ignoring the known path-prefix difference)
and fails if anything else differs. Two dispatch paths silently drifting apart is exactly the
kind of gap that produces a "why does Claude Code's `/supersaiyan run` behave differently from
the Codex fork" bug report months from now, with no obvious cause.

---

## 11. The status renderer's `attempt N/3` was a hardcoded literal, disconnected from `config.rebuild_cap`; `absolute_rebuild_ceiling` (item 9) was reconsidered and removed

**What happened:** watching issue #48 rebuild repeatedly (`loop:rebuild-2`, three
Building → QA → Review cycles with `reap: stale lock + assignee swept` events between
each), the dashboard consistently showed `attempt 3/3`. That number matched neither
config value in play: `rebuild_cap` was `2`, `absolute_rebuild_ceiling` was `4`. Traced
it to `super-board-status.py`'s `attempt_str()`/`rebuild_suffix()`:

```python
def attempt_str(item):
    return f"{min(rebuild_count(item) + 1, 3)}/3"
```

The `3` was a literal, not `rebuild_cap + 1` computed from the loaded config — the
script reads `cfg["project"]["owner"]` etc. but never reads `rebuild_cap` at all. It
happened to equal the correct value for the *original* default (`rebuild_cap=2` →
`2+1=3`), which is presumably how a hardcoded `3` ended up looking right in testing —
but changing `rebuild_cap` in config would never change what the dashboard displayed.

**Separately, on reflection:** item 9's `absolute_rebuild_ceiling` gate (added the
previous session as an independent hash-blind hard backstop, specifically to prevent a
card from rebuilding forever if every failure had a different root cause) was
reconsidered and removed. After walking through the reasoning again, the call was made
that `rebuild_cap` alone (hash-aware, with human-reauthorization already resetting the
counter per item 9) is the wanted safety property, and a second independent ceiling
added more configuration surface than value. This is a deliberate reversal of item 9's
second change, not a bug fix — see `absolute_rebuild_ceiling`'s removal from `run.md`'s
Halt gates table, decision list, and Root-cause-hash section.

**Status: fixed in the plugin itself** (marketplace + cache synced; local commits, not
yet pushed to `BankNatchapol/SuperSaiyan`). Three changes:

1. **`rebuild_cap` now supports `null` for unlimited.** Documented in
   `config-schema.json` and `run.md`: `rebuild_cap: null` means the card is never
   auto-blocked on the cap, no matter how many times an identical root-cause hash
   recurs. This is what actually satisfies "adjustable attempt count, with an unlimited
   option" — the ask that surfaced this whole investigation.
2. **`absolute_rebuild_ceiling` removed entirely** from `run.md` (Halt gates table,
   step-7 decision list, Root-cause-hash section) and `config-schema.json`, both
   duplicate copies (`skills/super-board/references/`, `skills/supersaiyan/references/`).
3. **`super-board-status.py` now reads `rebuild_cap` from the loaded config** and
   computes the denominator as `rebuild_cap + 1` (or renders no denominator at all when
   `rebuild_cap` is `null`), instead of hardcoding `3`. `attempt_str()` and
   `rebuild_suffix()` both take `rebuild_cap` as an explicit parameter now rather than
   reading a magic constant.

**Addendum, same session, found live on issue #48 itself:** fixing the hardcoded `3`
wasn't enough — the numerator was *also* silently capped. `attempt_str()`'s formula was
`min(rebuild_count + 1, rebuild_cap + 1)`, so once a card's true attempt count passed
the budget, the display froze at `budget/budget` forever instead of continuing to grow.
Issue #48 made this concrete: `loop:rebuild-6` (the 7th build attempt) still rendered as
`attempt 3/3`, indistinguishable from a card on its 3rd attempt. Cross-referencing every
QA/Review comment against the actual commits on PR #57's branch confirmed all 6
rebuilds carried genuinely distinct `root-cause-hash` values (`3d1ec6ec148e`,
`39787a969fc2`, `aa0a3851fff3`, `6b8bed27d8e0`, `aa1bb2bb4991`, `d083c1dde6c7`) — six
real, different AST-gate bypass techniques found by mutation-style QA, each with a
matching test added to `tests/test_score_separation.py`. So `rebuild_cap` was working
exactly as designed (no two consecutive identical failures, nothing to block on); the
dashboard just couldn't show that honestly.

Fixed by splitting the single capped number into two real, uncapped ones:

- **Total attempts** — `rebuild_count + 1`, never clamped. Now correctly shows `7`
  instead of freezing at `3`.
- **Same-issue streak** — how many *consecutive* attempts share the current
  `root-cause-hash`, computed by fetching each rebuild-labeled card's comments
  (`gh issue view --json comments`) and counting the trailing run of identical hashes
  (`trailing_hash_streak()`). This is the number `rebuild_cap` actually gates on, so
  showing it (`1/2` for issue #48, correctly) is what tells a human "how close to being
  blocked," which the frozen total never could.

Both `attempt_str()` and `rebuild_suffix()` now render `<total> total ·
<same-issue>/<rebuild_cap> same-issue` (fresh cards with no rebuild yet still show a
bare number, unchanged). The same-issue fetch shares its `gh issue view` call with the
existing Blocked/Skipped reason-tag fetch when a card needs both, so this doesn't double
the API cost for the common case (a blocked card usually got there via a repeated hash).
`status.md`'s locked-template spec was updated to match in both duplicate copies, synced
to cache.

**Upstream fix needed:** none beyond what's described above — caught and fixed live,
same session. The general lesson (item 10 still applies, and this makes a second
instance): any config value or gate condition that drives displayed behavior needs to
actually flow from the real source of truth into the renderer — not get reimplemented as
a literal, and not get silently clamped in a way that hides the exact situation (a
runaway card) the dashboard exists to surface.

---

## Summary table

| # | Problem | Status | Where the fix lives |
|---|---|---|---|
| 1 | Shared `worker_backend` config collision | Fixed (project-level workaround) | Per-tool config files |
| 2a | Rebuild-cap block after 2 failed attempts | Working as designed | N/A |
| 2b | Review Gate 1 bounces on already-fixed threads | **Open** | Needs `super-review` skill fix |
| 3 | Builders self-block on unmerged predecessors | Fixed | `strict_serial_ready_issue()` |
| 4 | Builder overwrites `.gitignore` from scratch | Fixed (project-level workaround) | `AGENTS.md` append-only rule |
| 5 | GROBID page-range reads only first coord group | Fixed | `tei.py` (domain code) |
| 6 | Fixed-tick polling exhausts GraphQL quota | Fixed, measured live (6s vs 600s) | Event-driven dispatch |
| 7 | No backend abstraction — dispatcher forked per tool | Working, but duplicated | Needs `Backend` interface |
| 8 | Orphan-guard pattern never matched real Cursor workers | Fixed, verified against a live process | Pattern + regression test |
| 9 | `rebuild_cap` never resets after human authorization; blocks fire regardless of hash | Fixed (plugin, local, unpushed) — hash-aware enforcement, verified live on issue #47. Originally paired with an `absolute_rebuild_ceiling` backstop, later removed — see #11. | `run.md` + `config-schema.json`, both copies |
| 10 | `run.md`/`config-schema.json` exist in two silently-divergent copies (`super-board` vs `supersaiyan` skills) | Fixed for this change; structural risk remains for future edits | Needs a single source of truth or a sync check |
| 11 | Dashboard's `attempt N/3` was a hardcoded, clamped literal — ignored `config.rebuild_cap` and froze once the true count passed it; `absolute_rebuild_ceiling` reconsidered and removed | Fixed (plugin, local, unpushed) — `rebuild_cap` supports `null` (unlimited); dashboard now shows uncapped total attempts AND the same-issue root-cause-hash streak, verified live against issue #48's 6 genuinely distinct rebuilds | `super-board-status.py`, `run.md` + `config-schema.json` (ceiling removed), `status.md`, all in both copies |

Items with no "upstream" location are things that had to be re-solved per project because
the fix lives in this repo's scripts/config rather than in the SuperSaiyan plugin itself.
Only #5 is genuinely project-specific; everything else in this list will recur for any other
project that adopts SuperSaiyan across multiple tools until it's fixed in the plugin.
