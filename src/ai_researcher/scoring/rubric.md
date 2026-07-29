# Evidence Quality Rubric

**Rubric version:** 2

This rubric scores the quality of the underlying scientific evidence, not the reliability
of the extraction pipeline. The five factors below total 100 points. Community attention,
pipeline confidence, and any other signal are excluded.

The YAML block is the executable source of the weights and thresholds. The scorer validates
it before use and derives the stored `rubric_version` from both the declared version and a
SHA-256 digest of this entire file. Any edit therefore changes the stored version.

<!-- rubric-yaml
version: "2"
factors:
  full_text:
    weight: 27
    values:
      parsed: 1.0
      abstract_only: 0.25
      other: 0.0
  peer_review:
    weight: 22
    values:
      peer_reviewed: 1.0
      preprint_or_unreviewed: 0.0
  directness:
    weight: 17
    values:
      direct: 1.0
      inferred: 0.0
  recency:
    weight: 17
    bands:
      - max_age_years: 2
        ratio: 1.0
      - max_age_years: 5
        ratio: 0.67
      - max_age_years: 10
        ratio: 0.33
      - ratio: 0.0
  replication:
    weight: 17
    bands:
      - min_distinct_supporting_papers: 3
        ratio: 1.0
      - min_distinct_supporting_papers: 2
        ratio: 0.5
      - min_distinct_supporting_papers: 0
        ratio: 0.0
-->

## Factors and justification

### Full text versus abstract-only — 27 points

`paper.parse_status = parsed` receives all 27 points. `abstract_only` receives 25% of this
factor: the claim remains scoreable, but methods, limitations, and surrounding
qualifications could not be inspected. Other parse states receive zero.

### Peer-reviewed versus preprint — 22 points

A paper receives 22 points only when `paper.is_preprint` is false and `paper.venue` is
present. A preprint or a paper without evidence of a reviewed venue receives zero. This is a
publication-status signal, not a judgment that peer review guarantees correctness.

### Direct statement versus inferred — 17 points

At least one supporting, passage-anchored `claim_evidence` record explicitly marked direct
receives 17 points. Evidence available only by inference receives zero. The flag is set
during evidence linking, alongside stance classification — the same LLM call that reads each
candidate node's body text to classify supports/refutes/mentions also judges whether that
node states the claim directly or requires an inferential step, in a single batched request.
The quality scorer does not infer directness from prose itself; it only reads the stored flag.

### Recency — 17 points

Age is computed from `paper.published_at` at scoring time. Papers at most two years old
receive 17 points, at most five years old receive 67%, at most ten years old receive 33%,
and older or undated papers receive zero. Recency is deliberately modest: older science is
not automatically poor science.

### Independent replication — 17 points

Replication counts distinct paper IDs among supporting evidence for the canonical claim,
never the number of passages. One supporting paper receives zero replication points, two
receive 50%, and three or more receive all 17 points. Refuting and mentioning evidence do not
increase this factor.

## Out of scope for v1

**Table/figure-backed versus narrative-only was considered and deliberately excluded.**
GROBID's TEI parsing (Phase 1) does not preserve any figure/table distinction — there is no
underlying signal to judge this factor against, structurally or via the LLM. Figure and table
grounding is explicitly out of scope for v1 (see `AGENTS.md`). Storing a value here with no
real signal behind it would be worse than omitting the factor: it would look like evidence
quality information when it is actually a constant placeholder. Revisit if a future phase adds
real figure/table parsing.
