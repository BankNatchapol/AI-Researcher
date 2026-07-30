"""Compute claim-extraction and stance metrics against a gold set."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_researcher.eval.goldset import GoldClaim
from ai_researcher.extraction.quantities import parse_quantity

ClaimLike = Mapping[str, Any] | Any


@dataclass(frozen=True, slots=True)
class ExtractedEvidenceObservation:
    """One evidence link produced by extraction / linking."""

    section_path: str
    stance: str


@dataclass(frozen=True, slots=True)
class ExtractedClaimObservation:
    """One extracted claim plus its linked evidence, for offline scoring."""

    id: int
    normalized_text: str
    object_value: float | None
    unit: str | None
    evidence: tuple[ExtractedEvidenceObservation, ...]


@dataclass(frozen=True, slots=True)
class ExtractionMetrics:
    """Stable extraction evaluation metrics — never blended with retrieval scores."""

    claim_precision: float
    claim_recall: float
    claim_f1: float
    evidence_span_precision: float
    stance_accuracy: float


def claims_match(extracted: ClaimLike, gold: GoldClaim) -> bool:
    """Return True when normalized text matches and numeric fields agree.

    Quantity comparison reuses ``parse_quantity`` so eval and dedup judge
    equality identically (including ``%`` → fraction normalization).
    """

    if _normalized_text(_field(extracted, "normalized_text")) != _normalized_text(
        gold.normalized_text
    ):
        return False

    gold_quantity = _normalized_quantity(gold.object_value, gold.unit)
    extracted_quantity = _normalized_quantity(
        _field(extracted, "object_value", default=None),
        _field(extracted, "unit", default=None),
    )
    if gold_quantity is None and extracted_quantity is None:
        return True
    if gold_quantity is None or extracted_quantity is None:
        return False
    return gold_quantity == extracted_quantity


def compute_extraction_metrics(
    gold_claims: Sequence[GoldClaim],
    extracted_claims: Sequence[ExtractedClaimObservation],
) -> ExtractionMetrics:
    """Score extracted claims and evidence against hand-labelled gold claims."""

    gold = tuple(gold_claims)
    extracted = tuple(extracted_claims)
    matches = _match_claims(gold, extracted)

    matched_extracted = len(matches)
    claim_precision = _ratio(matched_extracted, len(extracted))
    claim_recall = _ratio(matched_extracted, len(gold))
    claim_f1 = (
        0.0
        if claim_precision + claim_recall == 0.0
        else 2.0 * claim_precision * claim_recall / (claim_precision + claim_recall)
    )

    evidence_total = sum(len(claim.evidence) for claim in extracted)
    evidence_span_hits = 0
    stance_hits = 0
    stance_total = 0
    for gold_claim, extracted_claim in matches:
        for evidence in extracted_claim.evidence:
            stance_total += 1
            if evidence.section_path == gold_claim.section_path:
                evidence_span_hits += 1
            if evidence.stance == gold_claim.stance:
                stance_hits += 1

    return ExtractionMetrics(
        claim_precision=claim_precision,
        claim_recall=claim_recall,
        claim_f1=claim_f1,
        evidence_span_precision=_ratio(evidence_span_hits, evidence_total),
        stance_accuracy=_ratio(stance_hits, stance_total),
    )


def _match_claims(
    gold_claims: tuple[GoldClaim, ...],
    extracted_claims: tuple[ExtractedClaimObservation, ...],
) -> tuple[tuple[GoldClaim, ExtractedClaimObservation], ...]:
    """Greedy one-to-one matching of extracted claims onto gold claims."""

    used_gold: set[int] = set()
    matches: list[tuple[GoldClaim, ExtractedClaimObservation]] = []
    for extracted in extracted_claims:
        for gold_index, gold in enumerate(gold_claims):
            if gold_index in used_gold:
                continue
            if claims_match(extracted, gold):
                used_gold.add(gold_index)
                matches.append((gold, extracted))
                break
    return tuple(matches)


def _normalized_quantity(
    raw_value: object,
    raw_unit: object,
) -> tuple[float, str] | None:
    parsed_value, parsed_unit = parse_quantity(raw_value)  # type: ignore[arg-type]
    if parsed_value is None:
        return None
    unit = raw_unit if raw_unit not in (None, "") else parsed_unit
    normalized_unit = _normalized_text(unit)
    if normalized_unit in {"%", "percent", "percentage"}:
        return parsed_value / 100.0, ""
    return parsed_value, normalized_unit


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _field(claim: ClaimLike, field_name: str, *, default: Any = ...) -> Any:
    if isinstance(claim, Mapping):
        if default is ...:
            return claim[field_name]
        return claim.get(field_name, default)
    if default is ...:
        return getattr(claim, field_name)
    return getattr(claim, field_name, default)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


__all__ = [
    "ExtractedClaimObservation",
    "ExtractedEvidenceObservation",
    "ExtractionMetrics",
    "claims_match",
    "compute_extraction_metrics",
]
