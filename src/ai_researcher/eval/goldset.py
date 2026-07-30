"""Load and validate hand-labelled retrieval and extraction evaluation labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from sqlalchemy import select

from ai_researcher.db import connect
from ai_researcher.db.models import paper_scope, section
from ai_researcher.db.models import scope as scope_table

_VALID_STANCES = frozenset({"supports", "refutes", "mentions"})


class GoldSetValidationError(ValueError):
    """Raised when the gold set is malformed or names unavailable evidence."""


class SectionCatalog(Protocol):
    """Provide the section paths available to one saved scope."""

    def section_paths(self, scope: str) -> frozenset[str]:
        """Return every section path available in ``scope``."""


class PostgresSectionCatalog:
    """Read scope section paths from the single PostgreSQL store."""

    def section_paths(self, scope: str) -> frozenset[str]:
        """Return the known section paths for a saved scope."""

        with connect() as connection:
            paths = (
                connection.execute(
                    select(section.c.section_path)
                    .join(paper_scope, paper_scope.c.paper_id == section.c.paper_id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .where(scope_table.c.name == scope)
                )
                .scalars()
                .all()
            )
        return frozenset(str(path) for path in paths)


@dataclass(frozen=True, slots=True)
class GoldQuestion:
    """One question and the section paths labelled as genuine answers."""

    question: str
    scope: str
    section_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoldClaim:
    """One hand-labelled claim with its section anchor and expected stance."""

    normalized_text: str
    scope: str
    section_path: str
    stance: str
    object_value: float | None = None
    unit: str | None = None


def load_goldset(
    path: Path | str,
    *,
    scope: str | None = None,
    section_catalog: SectionCatalog | None = None,
) -> tuple[GoldQuestion, ...]:
    """Load a YAML gold set and optionally validate it against a scope corpus."""

    payload = _load_payload(path)
    records = payload.get("questions")
    if not isinstance(records, list) or not records:
        raise GoldSetValidationError(f"{Path(path)} must contain a non-empty questions list")

    questions: list[GoldQuestion] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise GoldSetValidationError(f"Question {index} must be a mapping")
        question = _required_text(record.get("question"), index, "question", kind="Question")
        question_scope = _required_text(record.get("scope"), index, "scope", kind="Question")
        section_paths = _section_paths(record.get("section_paths"), index)
        identity = (question_scope, question)
        if identity in seen:
            raise GoldSetValidationError(
                f"Question {index} duplicates a question in scope {question_scope!r}"
            )
        seen.add(identity)
        questions.append(
            GoldQuestion(
                question=question,
                scope=question_scope,
                section_paths=section_paths,
            )
        )

    selected = tuple(question for question in questions if scope is None or question.scope == scope)
    if scope is not None and not selected:
        raise GoldSetValidationError(f"No gold questions found for scope {scope!r}")
    if section_catalog is not None:
        _validate_question_section_matches(selected, section_catalog)
    return selected


def load_gold_claims(
    path: Path | str,
    *,
    scope: str | None = None,
    section_catalog: SectionCatalog | None = None,
) -> tuple[GoldClaim, ...]:
    """Load labelled claims from a YAML gold set and optionally validate anchors."""

    goldset_path = Path(path)
    payload = _load_payload(goldset_path)
    records = payload.get("claims")
    if not isinstance(records, list) or not records:
        raise GoldSetValidationError(f"{goldset_path} must contain a non-empty claims list")

    claims: list[GoldClaim] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise GoldSetValidationError(f"Claim {index} must be a mapping")
        normalized_text = _required_text(
            record.get("normalized_text"),
            index,
            "normalized_text",
            kind="Claim",
        )
        claim_scope = _required_text(record.get("scope"), index, "scope", kind="Claim")
        section_path = _required_text(
            record.get("section_path"),
            index,
            "section_path",
            kind="Claim",
        )
        stance = _required_text(record.get("stance"), index, "stance", kind="Claim")
        if stance not in _VALID_STANCES:
            raise GoldSetValidationError(
                f"Claim {index} has invalid stance {stance!r}; "
                f"expected one of {sorted(_VALID_STANCES)}"
            )
        identity = (claim_scope, normalized_text)
        if identity in seen:
            raise GoldSetValidationError(
                f"Claim {index} duplicates a claim in scope {claim_scope!r}"
            )
        seen.add(identity)
        claims.append(
            GoldClaim(
                normalized_text=normalized_text,
                scope=claim_scope,
                section_path=section_path,
                stance=stance,
                object_value=_optional_float(record.get("object_value"), index),
                unit=_optional_unit(record.get("unit"), index),
            )
        )

    selected = tuple(claim for claim in claims if scope is None or claim.scope == scope)
    if scope is not None and not selected:
        raise GoldSetValidationError(f"No gold claims found for scope {scope!r}")
    if section_catalog is not None:
        _validate_claim_section_matches(selected, section_catalog)
    return selected


def _load_payload(path: Path | str) -> dict:
    goldset_path = Path(path)
    try:
        payload = yaml.safe_load(goldset_path.read_text())
    except yaml.YAMLError as error:
        raise GoldSetValidationError(f"Invalid YAML in {goldset_path}: {error}") from error

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise GoldSetValidationError(f"{goldset_path} must contain gold-set version 1")
    return payload


def _required_text(value: object, index: int, field: str, *, kind: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise GoldSetValidationError(f"{kind} {index} has an invalid {field}")
    return normalized


def _section_paths(value: object, index: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GoldSetValidationError(f"Question {index} must have at least one section_path")
    paths: list[str] = []
    for path in value:
        normalized = path.strip() if isinstance(path, str) else ""
        if not normalized:
            raise GoldSetValidationError(f"Question {index} has an invalid section_path")
        if normalized not in paths:
            paths.append(normalized)
    return tuple(paths)


def _optional_float(value: object, index: int) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise GoldSetValidationError(f"Claim {index} has an invalid object_value")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise GoldSetValidationError(f"Claim {index} has an invalid object_value") from error


def _optional_unit(value: object, index: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GoldSetValidationError(f"Claim {index} has an invalid unit")
    normalized = value.strip()
    return normalized or None


def _validate_question_section_matches(
    questions: tuple[GoldQuestion, ...],
    section_catalog: SectionCatalog,
) -> None:
    paths_by_scope = {
        scope: section_catalog.section_paths(scope)
        for scope in {question.scope for question in questions}
    }
    for question in questions:
        known_paths = paths_by_scope[question.scope]
        for section_path in question.section_paths:
            if section_path not in known_paths:
                raise GoldSetValidationError(
                    f"Gold section_path {section_path!r} for {question.question!r} "
                    f"matches no section in scope {question.scope!r}"
                )


def _validate_claim_section_matches(
    claims: tuple[GoldClaim, ...],
    section_catalog: SectionCatalog,
) -> None:
    paths_by_scope = {
        scope: section_catalog.section_paths(scope) for scope in {claim.scope for claim in claims}
    }
    for claim in claims:
        known_paths = paths_by_scope[claim.scope]
        if claim.section_path not in known_paths:
            raise GoldSetValidationError(
                f"Gold section_path {claim.section_path!r} for {claim.normalized_text!r} "
                f"matches no section in scope {claim.scope!r}"
            )


__all__ = [
    "GoldClaim",
    "GoldQuestion",
    "GoldSetValidationError",
    "PostgresSectionCatalog",
    "SectionCatalog",
    "load_gold_claims",
    "load_goldset",
]
