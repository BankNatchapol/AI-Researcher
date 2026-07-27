"""Pydantic models for extraction records — every type requires a tree_node_id."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_researcher.extraction.quantities import parse_quantity

NonEmptyNodeId = Annotated[int, Field(gt=0)]


class _AnchoredRecord(BaseModel):
    """Base for every extraction record: passage anchor is mandatory."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tree_node_id: NonEmptyNodeId
    extraction_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)

    @field_validator("tree_node_id", mode="before")
    @classmethod
    def _reject_empty_anchor(cls, value: Any) -> Any:
        if value is None or value == "" or value == 0:
            msg = "tree_node_id is required and must be a non-empty node id"
            raise ValueError(msg)
        return value


class ClaimRecord(_AnchoredRecord):
    claim_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    subject: str | None = None
    predicate: str | None = None
    object_value: float | None = None
    unit: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _split_quantity(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        # Prefer an explicit unit when object_value is already numeric.
        raw_value = payload.get("object_value")
        raw_unit = payload.get("unit")
        if isinstance(raw_value, str):
            value, unit = parse_quantity(raw_value)
            payload["object_value"] = value
            if raw_unit is None or raw_unit == "":
                payload["unit"] = unit
        elif raw_value is not None and (raw_unit is None or raw_unit == ""):
            # Numeric with a unit suffix accidentally packed into a sibling string — leave as-is.
            pass
        return payload


class MethodRecord(_AnchoredRecord):
    method_text: str = Field(min_length=1)


class ResultRecord(_AnchoredRecord):
    result_text: str = Field(min_length=1)


class DatasetRecord(_AnchoredRecord):
    dataset_name: str = Field(min_length=1)
    description: str | None = None


class MetricRecord(_AnchoredRecord):
    metric_name: str = Field(min_length=1)
    object_value: float | None = None
    unit: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _split_quantity(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        raw_value = payload.get("object_value")
        raw_unit = payload.get("unit")
        if isinstance(raw_value, str):
            value, unit = parse_quantity(raw_value)
            payload["object_value"] = value
            if raw_unit is None or raw_unit == "":
                payload["unit"] = unit
        return payload


__all__ = [
    "ClaimRecord",
    "DatasetRecord",
    "MethodRecord",
    "MetricRecord",
    "ResultRecord",
]
