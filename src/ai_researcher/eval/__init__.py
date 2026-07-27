"""Retrieval evaluation against hand-labelled evidence sections."""

from ai_researcher.eval.goldset import (
    GoldQuestion,
    GoldSetValidationError,
    PostgresSectionCatalog,
    SectionCatalog,
    load_goldset,
)
from ai_researcher.eval.harness import (
    EvaluationMetrics,
    EvaluationResult,
    run_evaluation,
)

__all__ = [
    "EvaluationMetrics",
    "EvaluationResult",
    "GoldQuestion",
    "GoldSetValidationError",
    "PostgresSectionCatalog",
    "SectionCatalog",
    "load_goldset",
    "run_evaluation",
]
