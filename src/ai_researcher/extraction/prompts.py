"""Versioned extraction prompts for structured claim/method/result extraction."""

from __future__ import annotations

PROMPT_VERSION = "1"

EXTRACTION_INSTRUCTIONS = (
    "Extract claims, methods, results, datasets, and metrics from the provided "
    "paper section nodes. Every record MUST include tree_node_id referencing one "
    "of the provided nodes. Return structured records only."
)

__all__ = [
    "EXTRACTION_INSTRUCTIONS",
    "PROMPT_VERSION",
]
