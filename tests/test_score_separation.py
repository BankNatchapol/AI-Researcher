"""Mechanical build gates for score and evidence/discourse separation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "ai_researcher"
ARITHMETIC_CALLS = {
    "add",
    "and_",
    "average",
    "divmod",
    "floordiv",
    "fmean",
    "iadd",
    "iand",
    "ifloordiv",
    "ilshift",
    "imatmul",
    "imod",
    "imul",
    "ior",
    "ipow",
    "irshift",
    "isub",
    "itruediv",
    "ixor",
    "lshift",
    "matmul",
    "max",
    "mean",
    "median",
    "min",
    "mod",
    "mul",
    "or_",
    "pow",
    "prod",
    "rshift",
    "sub",
    "sum",
    "truediv",
    "xor",
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


def _nodes_in_scope(scope: ast.AST) -> tuple[ast.AST, ...]:
    nested_scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    nodes: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        if isinstance(node, nested_scopes):
            continue
        nodes.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return tuple(nodes)


def _assignment(node: ast.AST) -> tuple[tuple[ast.AST, ...], ast.AST] | None:
    if isinstance(node, ast.Assign):
        return tuple(node.targets), node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return (node.target,), node.value
    if isinstance(node, ast.NamedExpr):
        return (node.target,), node.value
    return None


def _target_names(targets: tuple[ast.AST, ...]) -> set[str]:
    return {
        descendant.id
        for target in targets
        for descendant in ast.walk(target)
        if isinstance(descendant, ast.Name)
    }


def _resolved_score_fields(
    node: ast.AST,
    aliases: dict[str, set[str]],
) -> set[str]:
    fields = _score_fields(node)
    for name in tuple(fields):
        fields.update(aliases.get(name, ()))
    return fields


def _score_aliases(nodes: tuple[ast.AST, ...]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            assignment = _assignment(node)
            if assignment is None:
                continue
            targets, value = assignment
            score_fields = _resolved_score_fields(value, aliases) & {
                "confidence",
                "evidence_quality",
            }
            if not score_fields:
                continue
            for target_name in _target_names(targets):
                previous = aliases.setdefault(target_name, set())
                before = len(previous)
                previous.update(score_fields)
                changed = changed or len(previous) != before
    return aliases


def test_no_module_performs_arithmetic_combining_the_two_scores() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scopes = (
            tree,
            *(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            ),
        )
        for scope in scopes:
            nodes = _nodes_in_scope(scope)
            aliases = _score_aliases(nodes)
            for node in nodes:
                is_arithmetic = isinstance(node, ast.BinOp) or (
                    isinstance(node, ast.Call) and _call_name(node) in ARITHMETIC_CALLS
                )
                if not is_arithmetic:
                    continue
                if {"confidence", "evidence_quality"} <= _resolved_score_fields(node, aliases):
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


@pytest.mark.parametrize(
    "arithmetic_call",
    (
        "operator.add",
        "operator.sub",
        "operator.mul",
        "operator.truediv",
        "operator.and_",
        "operator.or_",
        "operator.iand",
        "operator.ior",
        "pow",
    ),
)
def test_score_arithmetic_gate_detects_arithmetic_callables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arithmetic_call: str,
) -> None:
    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "import operator",
                "",
                "def blend(row):",
                f"    return {arithmetic_call}(row.confidence, row.evidence_quality)",
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


@pytest.mark.parametrize(
    "source",
    (
        "\n".join(
            (
                "import operator",
                "",
                "def blend(row):",
                "    combine = operator.add",
                "    return combine(row.confidence, row.evidence_quality)",
            )
        ),
        "\n".join(
            (
                "from operator import add as combine",
                "",
                "def blend(row):",
                "    return combine(row.confidence, row.evidence_quality)",
            )
        ),
    ),
)
def test_score_arithmetic_gate_detects_aliased_arithmetic_callables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    (tmp_path / "violation.py").write_text(source, encoding="utf-8")
    monkeypatch.setitem(
        test_no_module_performs_arithmetic_combining_the_two_scores.__globals__,
        "PACKAGE_ROOT",
        tmp_path,
    )

    with pytest.raises(AssertionError, match="score arithmetic combines"):
        test_no_module_performs_arithmetic_combining_the_two_scores()
