# Evidence Quality Rubric

**Rubric version:** 1

This rubric scores the quality of the underlying scientific evidence, not the reliability
of the extraction pipeline. The six factors below total 100 points. Community attention,
pipeline confidence, and any other signal are excluded.

The YAML block is the executable source of the weights and thresholds. The scorer validates
it before use and derives the stored `rubric_version` from both the declared version and a
SHA-256 digest of this entire file. Any edit therefore changes the stored version.

<!-- rubric-yaml
version: "1"
factors:
  full_text:
    weight: 25
    values:
      parsed: 1.0
      abstract_only: 0.25
      other: 0.0
  peer_review:
    weight: 20
    values:
      peer_reviewed: 1.0
      preprint_or_unreviewed: 0.0
  directness:
    weight: 15
    values:
      direct: 1.0
      inferred: 0.0
  evidence_presentation:
    weight: 10
    values:
      table_or_figure: 1.0
      narrative: 0.0
  recency:
    weight: 15
    bands:
      - max_age_years: 2
        ratio: 1.0
      - max_age_years: 5
        ratio: 0.67
      - max_age_years: 10
        ratio: 0.33
      - ratio: 0.0
  replication:
    weight: 15
    bands:
      - min_distinct_supporting_papers: 3
        ratio: 1.0
      - min_distinct_supporting_papers: 2
        ratio: 0.5
      - min_distinct_supporting_papers: 0
        ratio: 0.0
-->

## Factors and justification

### Full text versus abstract-only — 25 points

`paper.parse_status = parsed` receives all 25 points. `abstract_only` receives 25% of this
factor (6.25 points): the claim remains scoreable, but methods, limitations, and surrounding
qualifications could not be inspected. Other parse states receive zero.

### Peer-reviewed versus preprint — 20 points

A paper receives 20 points only when `paper.is_preprint` is false and `paper.venue` is
present. A preprint or a paper without evidence of a reviewed venue receives zero. This is a
publication-status signal, not a judgment that peer review guarantees correctness.

### Direct statement versus inferred — 15 points

At least one supporting, passage-anchored `claim_evidence` record explicitly marked direct
receives 15 points. Evidence available only by inference receives zero. The flag is an
extraction output; the quality scorer does not infer it from prose.

### Table/figure-backed versus narrative-only — 10 points

At least one supporting, passage-anchored evidence record marked as backed by a table or
figure receives 10 points. Narrative-only evidence receives zero. The flag is supplied by
extraction; this scorer performs no figure or table grounding.

### Recency — 15 points

Age is computed from `paper.published_at` at scoring time. Papers at most two years old
receive 15 points, at most five years old receive 67%, at most ten years old receive 33%,
and older or undated papers receive zero. Recency is deliberately modest: older science is
not automatically poor science.

### Independent replication — 15 points

Replication counts distinct paper IDs among supporting evidence for the canonical claim,
never the number of passages. One supporting paper receives zero replication points, two
receive 50%, and three or more receive all 15 points. Refuting and mentioning evidence do not
increase this factor.
