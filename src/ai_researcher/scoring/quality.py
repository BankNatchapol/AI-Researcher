"""Score the quality of a claim's scientific evidence from a written rubric."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from sqlalchemy import Connection, insert

from ai_researcher.db import connect
from ai_researcher.db.models import claim_score

RUBRIC_PATH = Path(__file__).with_name("rubric.md")
_RUBRIC_START = "<!-- rubric-yaml"
_RUBRIC_END = "-->"
_FACTOR_NAMES = {
    "full_text",
    "peer_review",
    "directness",
    "evidence_presentation",
    "recency",
    "replication",
}

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
ClaimLike = Mapping[str, Any] | Any
Stance = Literal["supports", "refutes", "mentions"]


@dataclass(frozen=True, slots=True)
class QualityEvidence:
    """One passage-anchored evidence input used by the written rubric."""

    tree_node_id: int
    paper_id: int
    stance: Stance
    is_direct: bool
    is_table_or_figure_backed: bool


@dataclass(frozen=True, slots=True)
class QualityClaim:
    """Paper metadata and evidence signals needed to score one claim."""

    id: int
    parse_status: str
    is_preprint: bool
    venue: str | None
    published_at: date | None
    evidence: tuple[QualityEvidence, ...]


@dataclass(frozen=True, slots=True)
class QualityFactor:
    """A named rubric signal and its weighted contribution."""

    name: str
    raw_value: int | float | str | bool | None
    contribution: float
    max_contribution: float


@dataclass(frozen=True, slots=True)
class QualityScore:
    """A bounded evidence-quality value and all of its rubric factors."""

    value: int
    rubric_version: str
    factors: tuple[QualityFactor, ...]

    @property
    def evidence_quality(self) -> int:
        """Alias matching the ``claim_score.evidence_quality`` column."""

        return self.value

    @property
    def score(self) -> int:
        """Convenience alias for callers rendering this score independently."""

        return self.value


@dataclass(frozen=True, slots=True)
class Rubric:
    """Validated executable configuration extracted from ``rubric.md``."""

    version: str
    factors: Mapping[str, Mapping[str, Any]]


class PostgresQualityStore:
    """Persist quality results as separate claim-score columns."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def save_quality(
        self,
        *,
        claim_id: int,
        confidence: int,
        quality: QualityScore,
    ) -> None:
        """Append one score snapshot without combining the independent values."""

        with self._connection_factory() as connection:
            connection.execute(
                insert(claim_score).values(
                    claim_id=_positive_integer(claim_id, "claim_id"),
                    confidence=_bounded_integer(confidence, "confidence"),
                    evidence_quality=quality.value,
                    rubric_version=quality.rubric_version,
                )
            )


def load_rubric(path: Path = RUBRIC_PATH) -> Rubric:
    """Load and validate the executable rubric and content-derived version."""

    content = path.read_bytes()
    text = content.decode("utf-8")
    start = text.find(_RUBRIC_START)
    if start < 0:
        raise ValueError(f"Rubric {path} is missing its executable YAML block")
    start += len(_RUBRIC_START)
    end = text.find(_RUBRIC_END, start)
    if end < 0:
        raise ValueError(f"Rubric {path} has an unterminated executable YAML block")
    payload = yaml.safe_load(text[start:end])
    if not isinstance(payload, Mapping):
        raise ValueError(f"Rubric {path} YAML must be a mapping")

    declared_version = str(payload.get("version", "")).strip()
    factors = payload.get("factors")
    if not declared_version:
        raise ValueError(f"Rubric {path} must declare a version")
    if not isinstance(factors, Mapping) or set(factors) != _FACTOR_NAMES:
        raise ValueError(f"Rubric {path} must define exactly the six evidence-quality factors")

    total_weight = 0.0
    validated_factors: dict[str, Mapping[str, Any]] = {}
    for name, configuration in factors.items():
        if not isinstance(configuration, Mapping):
            raise ValueError(f"Rubric factor {name} must be a mapping")
        weight = _number(configuration.get("weight"), f"{name}.weight")
        if weight < 0:
            raise ValueError(f"Rubric factor {name} weight must not be negative")
        total_weight += weight
        validated_factors[str(name)] = configuration
    if abs(total_weight - 100.0) > 1e-9:
        raise ValueError(f"Rubric weights must total 100, got {total_weight:g}")

    digest = hashlib.sha256(content).hexdigest()[:12]
    return Rubric(
        version=f"{declared_version}+sha256:{digest}",
        factors=validated_factors,
    )


def score_quality(
    claim: ClaimLike,
    *,
    rubric_path: Path = RUBRIC_PATH,
    as_of: date | None = None,
) -> QualityScore:
    """Return a 0–100 score using only factors declared in ``rubric.md``."""

    candidate = _coerce_claim(claim)
    rubric = load_rubric(rubric_path)
    score_date = date.today() if as_of is None else as_of
    supporting_evidence = tuple(item for item in candidate.evidence if item.stance == "supports")

    full_text_raw = candidate.parse_status
    peer_review_raw = (
        "peer_reviewed"
        if not candidate.is_preprint and candidate.venue is not None
        else "preprint_or_unreviewed"
    )
    directness_raw = "direct" if any(item.is_direct for item in supporting_evidence) else "inferred"
    presentation_raw = (
        "table_or_figure"
        if any(item.is_table_or_figure_backed for item in supporting_evidence)
        else "narrative"
    )
    age_years = (
        max(0.0, (score_date - candidate.published_at).days / 365.2425)
        if candidate.published_at is not None
        else None
    )
    supporting_paper_count = len({item.paper_id for item in supporting_evidence})

    factors = (
        _value_factor(rubric, "full_text", full_text_raw),
        _value_factor(rubric, "peer_review", peer_review_raw),
        _value_factor(rubric, "directness", directness_raw),
        _value_factor(rubric, "evidence_presentation", presentation_raw),
        _recency_factor(rubric, age_years),
        _replication_factor(rubric, supporting_paper_count),
    )
    value = max(0, min(100, round(sum(factor.contribution for factor in factors))))
    return QualityScore(
        value=value,
        rubric_version=rubric.version,
        factors=factors,
    )


def _value_factor(rubric: Rubric, name: str, raw_value: str) -> QualityFactor:
    configuration = rubric.factors[name]
    values = configuration.get("values")
    if not isinstance(values, Mapping):
        raise ValueError(f"Rubric factor {name} must define values")
    ratio = values.get(raw_value, values.get("other"))
    if ratio is None:
        raise ValueError(f"Rubric factor {name} does not define {raw_value!r}")
    return _factor(name, raw_value, _number(ratio, f"{name}.{raw_value}"), configuration)


def _recency_factor(rubric: Rubric, age_years: float | None) -> QualityFactor:
    name = "recency"
    configuration = rubric.factors[name]
    ratio = 0.0
    if age_years is not None:
        for band in _bands(configuration, name):
            maximum = band.get("max_age_years")
            if maximum is None or age_years <= _number(maximum, f"{name}.max_age_years"):
                ratio = _number(band.get("ratio"), f"{name}.ratio")
                break
    return _factor(name, age_years, ratio, configuration)


def _replication_factor(rubric: Rubric, paper_count: int) -> QualityFactor:
    name = "replication"
    configuration = rubric.factors[name]
    ratio = 0.0
    for band in _bands(configuration, name):
        minimum = _number(
            band.get("min_distinct_supporting_papers"),
            f"{name}.min_distinct_supporting_papers",
        )
        if paper_count >= minimum:
            ratio = _number(band.get("ratio"), f"{name}.ratio")
            break
    return _factor(name, paper_count, ratio, configuration)


def _factor(
    name: str,
    raw_value: int | float | str | bool | None,
    ratio: float,
    configuration: Mapping[str, Any],
) -> QualityFactor:
    weight = _number(configuration.get("weight"), f"{name}.weight")
    return QualityFactor(
        name=name,
        raw_value=raw_value,
        contribution=round(max(0.0, min(1.0, ratio)) * weight, 4),
        max_contribution=weight,
    )


def _bands(configuration: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    bands = configuration.get("bands")
    if not isinstance(bands, list) or not bands:
        raise ValueError(f"Rubric factor {name} must define non-empty bands")
    if not all(isinstance(band, Mapping) for band in bands):
        raise ValueError(f"Rubric factor {name} bands must be mappings")
    return cast(list[Mapping[str, Any]], bands)


def _coerce_claim(claim: ClaimLike) -> QualityClaim:
    if isinstance(claim, QualityClaim):
        return claim
    published_at = _field(claim, "published_at", default=None)
    if isinstance(published_at, str):
        published_at = date.fromisoformat(published_at)
    if published_at is not None and not isinstance(published_at, date):
        raise ValueError("Claim published_at must be a date, ISO date string, or None")

    evidence: list[QualityEvidence] = []
    for raw_evidence in _field(claim, "evidence", default=()):
        if isinstance(raw_evidence, QualityEvidence):
            evidence.append(raw_evidence)
            continue
        stance = str(_field(raw_evidence, "stance"))
        if stance not in {"supports", "refutes", "mentions"}:
            raise ValueError(f"Unsupported evidence stance: {stance}")
        evidence.append(
            QualityEvidence(
                tree_node_id=_positive_integer(
                    _field(raw_evidence, "tree_node_id"),
                    "tree_node_id",
                ),
                paper_id=_positive_integer(_field(raw_evidence, "paper_id"), "paper_id"),
                stance=cast(Stance, stance),
                is_direct=_boolean(_field(raw_evidence, "is_direct"), "is_direct"),
                is_table_or_figure_backed=_boolean(
                    _field(raw_evidence, "is_table_or_figure_backed"),
                    "is_table_or_figure_backed",
                ),
            )
        )

    venue = _field(claim, "venue", default=None)
    normalized_venue = str(venue).strip() if venue is not None else None
    return QualityClaim(
        id=_positive_integer(_field(claim, "id"), "id"),
        parse_status=str(_field(claim, "parse_status")).strip(),
        is_preprint=_boolean(_field(claim, "is_preprint"), "is_preprint"),
        venue=normalized_venue or None,
        published_at=published_at,
        evidence=tuple(evidence),
    )


def _field(value: ClaimLike, field_name: str, *, default: Any = ...) -> Any:
    if isinstance(value, Mapping):
        if default is ...:
            return value[field_name]
        return value.get(field_name, default)
    if default is ...:
        return getattr(value, field_name)
    return getattr(value, field_name, default)


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric") from error


def _positive_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if integer < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return integer


def _bounded_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer from 0 to 100")
    try:
        integer = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer from 0 to 100") from error
    if not 0 <= integer <= 100:
        raise ValueError(f"{field_name} must be an integer from 0 to 100")
    return integer


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


__all__ = [
    "PostgresQualityStore",
    "QualityClaim",
    "QualityEvidence",
    "QualityFactor",
    "QualityScore",
    "RUBRIC_PATH",
    "Rubric",
    "load_rubric",
    "score_quality",
]
