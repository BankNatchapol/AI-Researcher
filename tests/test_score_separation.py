"""Mechanical build gates for score and evidence/discourse separation."""

from __future__ import annotations

import ast
from pathlib import Path

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
                modules = [node.module or ""]
            if any(module == "discourse" or ".discourse" in module for module in modules):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

    assert violations == [], "scoring imports discourse: " + ", ".join(violations)
