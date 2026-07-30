"""Markdown rendering for temporal digests — two separated channels."""

from __future__ import annotations

from ai_researcher.digest.build import CommunityMention, Digest


def render_digest(digest: Digest) -> str:
    """Render Evidence and Community attention as fixed top-level sections."""

    lines: list[str] = [
        f"# Digest since {digest.since.isoformat()}",
        "",
        "## Evidence",
        "",
    ]
    evidence_lines = _evidence_lines(digest)
    if evidence_lines:
        lines.extend(evidence_lines)
    else:
        lines.append("Nothing changed in this window.")
    lines.extend(["", "## Community attention", ""])
    lines.append(
        "Attention is not evidence of validity — counts measure interest, not scientific merit."
    )
    lines.append("")
    community_lines = _community_lines(digest.community)
    if community_lines:
        lines.extend(community_lines)
    else:
        lines.append("Nothing changed in this window.")
    lines.append("")
    return "\n".join(lines)


def _evidence_lines(digest: Digest) -> list[str]:
    lines: list[str] = []
    changes = digest.changes
    refs = digest.paper_refs

    if changes.new_papers:
        lines.append("### New papers")
        for item in changes.new_papers:
            ref = refs.get(item.paper_id, f"paper #{item.paper_id}")
            lines.append(f"- {ref} (scope #{item.scope_id})")
        lines.append("")

    if changes.new_evidence:
        lines.append("### New evidence")
        for item in changes.new_evidence:
            lines.append(
                f"- Claim #{item.claim_id}: {item.stance} (evidence #{item.claim_evidence_id})"
            )
        lines.append("")

    if changes.stance_flips:
        lines.append("### Stance flips")
        for item in changes.stance_flips:
            lines.append(
                f"- Claim #{item.claim_id} gained first refutes evidence "
                f"(#{item.claim_evidence_id})"
            )
        lines.append("")

    if changes.score_movements:
        lines.append("### Score movement")
        for item in changes.score_movements:
            lines.append(f"- Claim #{item.claim_id}:")
            lines.append(f"  - confidence: {item.confidence_before} → {item.confidence_after}")
            lines.append(
                "  - evidence_quality: "
                f"{item.evidence_quality_before} → {item.evidence_quality_after}"
            )
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _community_lines(mentions: tuple[CommunityMention, ...]) -> list[str]:
    lines: list[str] = []
    for item in mentions:
        label = (item.title or "").strip() or item.url
        link = f"[{label}]({item.url})"
        details: list[str] = []
        if item.score is not None:
            details.append(f"score {item.score}")
        if item.num_comments is not None:
            details.append(f"{item.num_comments} comments")
        details.append(f"paper #{item.paper_id}, claim #{item.claim_id}")
        lines.append(f"- {link} — {', '.join(details)}")
    return lines
