# SciRate spike — compliant signal-only fetch

**Date:** 2026-07-30  
**Task:** phase-4 / `12-scirate-spike` (issue #71)  
**Status:** deferred — adapter ships disabled by default

## Outcome

A polite, identifying HTTP GET to SciRate paper pages fails with **Cloudflare 403
(challenge)** for non-browser clients. The same 403 is returned with a browser-like
User-Agent. No compliant signal-only fetch path is available within the time box.

The `scirate` discourse adapter is implemented and **registered**, but remains
**disabled unless `DISCOURSE_SCIRATE_ENABLED=true`**. With the flag unset,
`airesearch sweep --kind discourse` never contacts `scirate.com`.

## Approach attempted

1. **robots.txt / content signals** — confirmed still:
   - `Content-Signal: search=yes, ai-train=no, use=reference`
   - `Allow: /` for `User-agent: *`
   - `ai-input` unspecified
2. **Polite GET** of `https://scirate.com/arxiv/<id>` with identifying UA
   `AI-Researcher/0.1 (mailto:<CONTACT_EMAIL>)`.
3. **Browser-like UA** retry — still `HTTP/2 403` with `cf-mitigated: challenge`.
4. **No dependency** on the dead `scirate` PyPI package (v0.1.0, April 2018, HTML scrape).
5. **Adapter design (ready if access opens):**
   - Key by arXiv ID → `https://scirate.com/arxiv/{id}`
   - Parse numeric scite count only (`N scites`); store `external_id`, `url`, `score`
   - Never store page body/title/author; never use content for training
   - Conservative rate limit (`SCIRATE_MIN_INTERVAL_SECONDS`, default 5s)
   - Silent degrade on 403 / network errors

## Live probe (2026-07-30)

```
GET https://scirate.com/arxiv/2402.05555
UA: AI-Researcher/0.1 (mailto:researcher@example.com)
→ HTTP/2 403, server: cloudflare, cf-mitigated: challenge

GET (browser UA)
→ HTTP/2 403, same challenge
```

## Recommendation

**Defer SciRate ingestion.** Keep the adapter disabled. Do not add browser automation
or bot-detection circumvention. Revisit only if SciRate publishes a documented API /
machine-readable export, or Cloudflare stops challenging non-interactive clients for
signal-only GETs consistent with `use=reference`.

Naming reminder: SciRate "scites" are attention upvotes — unrelated to scite.ai Smart
Citations — and must never enter `scoring/` / `claim_score`.
