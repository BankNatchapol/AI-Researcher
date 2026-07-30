"""Mechanical build gates for score and evidence/discourse separation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "ai_researcher"
ARITHMETIC_CALLS = {
    "average",
    "fmean",
    "max",
    "mean",
    "median",
    "min",
    "prod",
    "sum",
}


def _score_fields(node: ast.AST) -> set[str]:
    fields: set[str] = set()
    for descendant in ast.walk(node):
        if isinstance(descendant, ast.Name):
            fields.add(descendant.id)
        elif isinstance(descendant, ast.Attribute):
            fields.add(descendant.attr)
        elif (
            isinstance(descendant, ast.Subscript)
            and isinstance(descendant.slice, ast.Constant)
            and isinstance(descendant.slice.value, str)
        ):
            fields.add(descendant.slice.value)
        elif isinstance(descendant, ast.keyword) and descendant.arg:
            fields.add(descendant.arg)
    return fields


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_no_module_performs_arithmetic_combining_the_two_scores() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            is_arithmetic = isinstance(node, ast.BinOp) or (
                isinstance(node, ast.Call) and _call_name(node) in ARITHMETIC_CALLS
            )
            if not is_arithmetic:
                continue
            if {"confidence", "evidence_quality"} <= _score_fields(node):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

    message = "score arithmetic combines confidence and evidence_quality: " + ", ".join(violations)
    assert violations == [], message


def test_scoring_package_does_not_import_discourse() -> None:
    violations: list[str] = []
    scoring_root = PACKAGE_ROOT / "scoring"
    for path in sorted(scoring_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base_module = node.module or ""
                modules = [
                    base_module,
                    *(
                        f"{base_module}.{alias.name}" if base_module else alias.name
                        for alias in node.names
                    ),
                ]
            if any(module == "discourse" or ".discourse" in module for module in modules):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

    assert violations == [], "scoring imports discourse: " + ", ".join(violations)


def test_discourse_gate_detects_from_package_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring_root = tmp_path / "scoring"
    scoring_root.mkdir()
    (scoring_root / "violation.py").write_text(
        "from ai_researcher import discourse\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(
        test_scoring_package_does_not_import_discourse.__globals__,
        "PACKAGE_ROOT",
        tmp_path,
    )

    with pytest.raises(AssertionError, match="scoring imports discourse"):
        test_scoring_package_does_not_import_discourse()


def test_score_arithmetic_gate_detects_aliased_score_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "def blend(row):",
                "    pipeline = row.confidence",
                "    science = row.evidence_quality",
                "    return (pipeline + science) / 2",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        test_no_module_performs_arithmetic_combining_the_two_scores.__globals__,
        "PACKAGE_ROOT",
        tmp_path,
    )

    with pytest.raises(AssertionError, match="score arithmetic combines"):
        test_no_module_performs_arithmetic_combining_the_two_scores()
