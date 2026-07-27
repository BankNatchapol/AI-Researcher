"""Load and validate hand-labelled retrieval evaluation questions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from sqlalchemy import select

from ai_researcher.db import connect
from ai_researcher.db.models import paper_scope, section
from ai_researcher.db.models import scope as scope_table


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


def load_goldset(
    path: Path | str,
    *,
    scope: str | None = None,
    section_catalog: SectionCatalog | None = None,
) -> tuple[GoldQuestion, ...]:
    """Load a YAML gold set and optionally validate it against a scope corpus."""

    goldset_path = Path(path)
    try:
        payload = yaml.safe_load(goldset_path.read_text())
    except yaml.YAMLError as error:
        raise GoldSetValidationError(f"Invalid YAML in {goldset_path}: {error}") from error

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise GoldSetValidationError(f"{goldset_path} must contain gold-set version 1")
    records = payload.get("questions")
    if not isinstance(records, list) or not records:
        raise GoldSetValidationError(f"{goldset_path} must contain a non-empty questions list")

    questions: list[GoldQuestion] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise GoldSetValidationError(f"Question {index} must be a mapping")
        question = _required_text(record.get("question"), index, "question")
        question_scope = _required_text(record.get("scope"), index, "scope")
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
        _validate_section_matches(selected, section_catalog)
    return selected


def _required_text(value: object, index: int, field: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise GoldSetValidationError(f"Question {index} has an invalid {field}")
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


def _validate_section_matches(
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


__all__ = [
    "GoldQuestion",
    "GoldSetValidationError",
    "PostgresSectionCatalog",
    "SectionCatalog",
    "load_goldset",
]
