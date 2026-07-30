"""Retrieval and extraction evaluation against hand-labelled evidence."""

from ai_researcher.eval.extraction_metrics import (
    ExtractedClaimObservation,
    ExtractedEvidenceObservation,
    ExtractionMetrics,
    claims_match,
    compute_extraction_metrics,
)
from ai_researcher.eval.goldset import (
    GoldClaim,
    GoldQuestion,
    GoldSetValidationError,
    PostgresSectionCatalog,
    SectionCatalog,
    load_gold_claims,
    load_goldset,
)
from ai_researcher.eval.harness import (
    EvaluationMetrics,
    EvaluationResult,
    ExtractionEvaluationResult,
    load_extracted_claims,
    run_evaluation,
    run_extraction_evaluation,
)

__all__ = [
    "EvaluationMetrics",
    "EvaluationResult",
    "ExtractedClaimObservation",
    "ExtractedEvidenceObservation",
    "ExtractionEvaluationResult",
    "ExtractionMetrics",
    "GoldClaim",
    "GoldQuestion",
    "GoldSetValidationError",
    "PostgresSectionCatalog",
    "SectionCatalog",
    "claims_match",
    "compute_extraction_metrics",
    "load_extracted_claims",
    "load_gold_claims",
    "load_goldset",
    "run_evaluation",
    "run_extraction_evaluation",
]
