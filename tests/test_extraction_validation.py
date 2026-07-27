"""Tests for extraction pydantic models, quantity parsing, and batch validation."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from ai_researcher.extraction.quantities import parse_quantity
from ai_researcher.extraction.schema import (
    ClaimRecord,
    DatasetRecord,
    MethodRecord,
    MetricRecord,
    ResultRecord,
)
from ai_researcher.extraction.validate import (
    MissingAnchorError,
    ValidationOutcome,
    validate_batch,
    validate_llm_output,
)

ALLOWED_NODE_IDS = frozenset({101, 102, 103})


def _valid_claim(**overrides: Any) -> dict[str, Any]:
    base = {
        "record_type": "claim",
        "tree_node_id": 101,
        "claim_text": "Surface code threshold is about 1%.",
        "normalized_text": "surface code threshold is about 1%",
        "claim_type": "threshold",
        "subject": "surface code",
        "predicate": "has_threshold",
        "object_value": "1%",
        "extraction_model": "test-model",
        "prompt_version": "v1",
    }
    base.update(overrides)
    return base


def test_models_require_non_empty_tree_node_id() -> None:
    for model_cls, payload in (
        (
            ClaimRecord,
            {
                "tree_node_id": 1,
                "claim_text": "c",
                "normalized_text": "c",
                "claim_type": "fact",
                "extraction_model": "m",
                "prompt_version": "v1",
            },
        ),
        (
            MethodRecord,
            {
                "tree_node_id": 1,
                "method_text": "m",
                "extraction_model": "m",
                "prompt_version": "v1",
            },
        ),
        (
            ResultRecord,
            {
                "tree_node_id": 1,
                "result_text": "r",
                "extraction_model": "m",
                "prompt_version": "v1",
            },
        ),
        (
            DatasetRecord,
            {
                "tree_node_id": 1,
                "dataset_name": "d",
                "extraction_model": "m",
                "prompt_version": "v1",
            },
        ),
        (
            MetricRecord,
            {
                "tree_node_id": 1,
                "metric_name": "acc",
                "extraction_model": "m",
                "prompt_version": "v1",
            },
        ),
    ):
        assert model_cls.model_validate(payload).tree_node_id == 1
        with pytest.raises(Exception):
            model_cls.model_validate({**payload, "tree_node_id": None})
        with pytest.raises(Exception):
            model_cls.model_validate({k: v for k, v in payload.items() if k != "tree_node_id"})


def test_valid_record_passes_validation() -> None:
    outcome = validate_batch([_valid_claim()], ALLOWED_NODE_IDS)
    assert isinstance(outcome, ValidationOutcome)
    assert outcome.paper_failed is False
    assert len(outcome.accepted) == 1
    assert outcome.rejected == []
    record = outcome.accepted[0]
    assert isinstance(record, ClaimRecord)
    assert record.tree_node_id == 101
    assert record.object_value == pytest.approx(1.0)
    assert record.unit == "%"


def test_missing_tree_node_id_is_named_error_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = _valid_claim()
    del raw["tree_node_id"]
    with caplog.at_level(logging.WARNING):
        outcome = validate_batch([raw], ALLOWED_NODE_IDS)
    assert outcome.accepted == []
    assert len(outcome.rejected) == 1
    rejection = outcome.rejected[0]
    assert isinstance(rejection.error, MissingAnchorError)
    assert (
        "tree_node_id" in str(rejection.error).lower() or "anchor" in str(rejection.error).lower()
    )
    assert any("tree_node_id" in r.message or "anchor" in r.message.lower() for r in caplog.records)


def test_foreign_tree_node_id_is_rejected_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = _valid_claim(tree_node_id=999)
    with caplog.at_level(logging.WARNING):
        outcome = validate_batch([raw], ALLOWED_NODE_IDS)
    assert outcome.accepted == []
    assert len(outcome.rejected) == 1
    assert isinstance(outcome.rejected[0].error, MissingAnchorError)
    assert any("999" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ("text", "expected_value", "expected_unit"),
    [
        ("1%", 1.0, "%"),
        ("0.01", 0.01, None),
        ("1e-2", 0.01, None),
    ],
)
def test_parse_quantity_numeric_unit_variants(
    text: str, expected_value: float, expected_unit: str | None
) -> None:
    value, unit = parse_quantity(text)
    assert value == pytest.approx(expected_value)
    assert unit == expected_unit


def test_unparseable_json_retries_once_then_paper_failure_without_raising() -> None:
    calls = {"n": 0}

    def fetch() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "not-json{{{{"
        return "still-not-json"

    outcome = validate_llm_output(fetch, ALLOWED_NODE_IDS)
    assert calls["n"] == 2
    assert outcome.paper_failed is True
    assert outcome.accepted == []
    assert outcome.failure_reason is not None


def test_malformed_then_valid_on_retry_accepts() -> None:
    calls = {"n": 0}
    good = json.dumps({"records": [_valid_claim()]})

    def fetch() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "{broken"
        return good

    outcome = validate_llm_output(fetch, ALLOWED_NODE_IDS)
    assert calls["n"] == 2
    assert outcome.paper_failed is False
    assert len(outcome.accepted) == 1
