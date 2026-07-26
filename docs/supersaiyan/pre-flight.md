# Pre-flight — ai-researcher-app Phase 1

Generated: 2026-07-26 · Board: [AI-Researcher #6](https://github.com/users/BankNatchapol/projects/6)

Each unchecked `[ ]` is a halt gate. `supersaiyan run` refuses to start until every item
is `[✓]`.

## 🔑 Credentials the loop will need

- [ ] **LLM API key** — `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (issues #4, #7)
      Not set in the current shell. The LiteLLM gateway (#4) and the scoping dialogue (#7)
      both fail without one. Add it to `.env` once #1 creates `.env.example`.
- [ ] **`CONTACT_EMAIL`** (issue #5)
      Sent in the User-Agent of every scholarly API request. OpenAlex and Crossref both
      expect a contact address for polite-pool access; without it, expect throttling.
- [ ] **`DATABASE_URL`** (issues #2, #3)
      Written by #2's Docker Compose setup. Not needed before then.
- [ ] **`GROBID_URL`** (issues #2, #9)
      Written by #2. Defaults to `http://localhost:8070`.
- [ ] **`STORAGE_DIR`** (issue #8)
      Local directory for downloaded PDFs. Choose a path with room for ~1,000 papers.

No Reddit, Hugging Face, or SciRate credentials are needed in Phase 1 — those arrive in
Phase 4.

## 🛠 Tools the loop will need

- [✓] `uv` 0.11.25 (verified)
- [✓] `docker` 29.2.1 with Compose v2 (verified)
- [✓] `gh` 2.83.2, authenticated with `project`, `repo` scopes (verified)
- [✓] `jq` 1.7.1 (verified)
- [✓] `git` 2.50.1 (verified)
- [✓] Python 3.14.2 — satisfies the 3.11+ floor (verified)
- [ ] **Docker daemon running**
      Installed but **not currently running**. Issue #2 cannot pass its health-check
      acceptance criteria until Docker Desktop is started, and #3, #9, #10, #11 all depend
      on Postgres being reachable. Start Docker Desktop before running the loop.

## 🌐 Environment

- [✓] GitHub repo reachable: https://github.com/BankNatchapol/AI-Researcher
- [✓] Project board reachable: AI-Researcher #6, Status field has all 7 columns
- [ ] **Postgres reachable** — blocked on the Docker daemon; created by issue #2
- [ ] **GROBID reachable** on `:8070` — blocked on the Docker daemon; created by issue #2
- [ ] **Scholarly APIs reachable** — arXiv, OpenAlex, Semantic Scholar (issue #5)
      All three are public and keyless. Adapter tests run offline against fixtures, so this
      only gates the live `ingest` acceptance criteria in #10.

## Notes for the loop

- **Python version:** the system Python is 3.14.2, well above the 3.11 floor. `uv` pins the
  project version independently, so this is informational only.
- **GROBID image:** must be an arm64 build (Apple Silicon). Issue #2's acceptance criteria
  require both images to resolve on `linux/arm64` without emulation warnings.
- **Order matters:** issues #1–#11 form a strict dependency chain. #2 gates everything that
  touches the database or GROBID.

## Summary

**2 halt gates before the loop can run cleanly:**

1. Start the Docker daemon (Docker Desktop)
2. Set an LLM API key in the environment or `.env`

The remaining unchecked items are produced by the tasks themselves and are not blockers.
