"""Terminal rendering for claims with two independently labelled score columns."""

from __future__ import annotations

from collections.abc import Sequence

from ai_researcher.claims.query import ClaimDetail, ClaimSummary, ScoreFactor


def render_claims_table(claims: Sequence[ClaimSummary]) -> str:
    """Render a claims list with separate confidence and evidence_quality columns."""

    headers = (
        "id",
        "type",
        "confidence",
        "evidence_quality",
        "replication",
        "claim",
    )
    rows = [
        (
            str(claim.id),
            claim.claim_type,
            str(claim.confidence),
            str(claim.evidence_quality),
            str(claim.replication_count),
            _one_line(claim.claim_text),
        )
        for claim in claims
    ]
    if not rows:
        return "\t".join(headers) + "\n(no claims)"

    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    lines = [_format_row(headers, widths)]
    lines.extend(_format_row(row, widths) for row in rows)
    return "\n".join(lines)


def render_claim_detail(claim: ClaimDetail) -> str:
    """Render one claim with both score factor lists and linked evidence."""

    sections = [
        f"Claim {claim.id}",
        f"Type: {claim.claim_type}",
        f"Paper: {claim.paper_id}",
        f"Text: {claim.claim_text}",
        f"Replication count: {claim.replication_count}",
        "",
        f"confidence: {claim.confidence}",
        *_render_factors("confidence factors", claim.confidence_factors),
        "",
        f"evidence_quality: {claim.evidence_quality}",
        *_render_factors("evidence_quality factors", claim.evidence_quality_factors),
        "",
        "Evidence",
    ]
    if not claim.evidence:
        sections.append("(none)")
    else:
        for item in claim.evidence:
            citation = (
                item.citation.rendered
                if item.citation is not None
                else (f"node {item.tree_node_id} / paper {item.paper_id}")
            )
            sections.append(f"- [{item.stance}] {citation}")
            sections.append(f'  rationale: "{item.rationale_text}"')
    return "\n".join(sections)


def _render_factors(heading: str, factors: Sequence[ScoreFactor]) -> list[str]:
    lines = [f"{heading}:"]
    if not factors:
        lines.append("  (none)")
        return lines
    for factor in factors:
        lines.append(
            f"  - {factor.name}: raw={factor.raw_value!r} "
            f"contribution={factor.contribution}/{factor.max_contribution}"
        )
    return lines


def _format_row(cells: Sequence[str], widths: Sequence[int]) -> str:
    return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells))


def _one_line(text: str) -> str:
    return " ".join(text.split())


__all__ = ["render_claim_detail", "render_claims_table"]
