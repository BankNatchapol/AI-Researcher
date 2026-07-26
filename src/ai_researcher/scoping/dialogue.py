"""Interactive narrowing dialogue for a new research scope."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from ai_researcher.llm import gateway
from ai_researcher.scoping import ScopeDefinition
from ai_researcher.scoping.estimate import estimate_scope

_PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "subtopics": {"type": "array", "items": {"type": "string"}},
        "adjacent_terms": {"type": "array", "items": {"type": "string"}},
        "exclusions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subtopics", "adjacent_terms", "exclusions"],
    "additionalProperties": False,
}


class InvalidScopingProposalError(ValueError):
    """Raised when the model does not return the requested proposal shape."""


def run_dialogue(
    initial_scope: ScopeDefinition,
    *,
    confirm: Callable[[str], bool],
    emit: Callable[[str], None],
    complete_fn: Callable[..., str | dict] | None = None,
    estimate_fn: Callable[[ScopeDefinition], int] | None = None,
) -> ScopeDefinition:
    """Propose and apply user-approved narrowing decisions."""

    complete = gateway.complete if complete_fn is None else complete_fn
    estimate = estimate_scope if estimate_fn is None else estimate_fn
    current = initial_scope
    initial_count = estimate(current)
    emit(f"Estimated candidates before narrowing: {initial_count}")

    response = complete(
        [
            {
                "role": "user",
                "content": _proposal_prompt(current, initial_count),
            }
        ],
        job="scoping",
        schema=_PROPOSAL_SCHEMA,
    )
    proposal = _validated_proposal(response)

    decisions = (
        ("sub-topic", proposal["subtopics"], "include_terms"),
        ("adjacent term", proposal["adjacent_terms"], "include_terms"),
        ("exclusion", proposal["exclusions"], "exclude_terms"),
    )
    for label, terms, target_field in decisions:
        for term in terms:
            emit(f"Proposed {label}: {term}")
            if not confirm(f"Accept {label} '{term}'?"):
                continue
            current = _append_term(current, target_field, term)
            count = estimate(current)
            emit(f"Estimated candidates after accepting {label} '{term}': {count}")
    return current


def _proposal_prompt(scope: ScopeDefinition, initial_count: int) -> str:
    return (
        "Help a quantum-computing and AI researcher narrow a literature scope. "
        "Propose concise sub-topics, adjacent search terms, and explicit exclusions. "
        "Return only the requested structured object.\n\n"
        f"Scope name: {scope.name}\n"
        f"Description: {scope.description}\n"
        f"Current include terms: {', '.join(scope.include_terms)}\n"
        f"Current exclusions: {', '.join(scope.exclude_terms) or '(none)'}\n"
        f"arXiv categories: {', '.join(scope.categories) or '(none)'}\n"
        f"Trial candidate estimate: {initial_count}"
    )


def _validated_proposal(response: str | dict) -> dict[str, tuple[str, ...]]:
    if not isinstance(response, dict):
        raise InvalidScopingProposalError("Scoping model must return a structured object")
    proposal: dict[str, tuple[str, ...]] = {}
    for key in ("subtopics", "adjacent_terms", "exclusions"):
        values = response.get(key)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise InvalidScopingProposalError(f"Scoping proposal field {key!r} must be a list")
        proposal[key] = tuple(_unique_nonempty(values))
    return proposal


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def _append_term(
    scope: ScopeDefinition,
    field_name: str,
    term: str,
) -> ScopeDefinition:
    current_terms = getattr(scope, field_name)
    if term.casefold() in {current.casefold() for current in current_terms}:
        return scope
    return replace(scope, **{field_name: (*current_terms, term)})


__all__ = ["InvalidScopingProposalError", "run_dialogue"]
