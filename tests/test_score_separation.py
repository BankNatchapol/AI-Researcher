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
} | {
    f"__{prefix}{operation}__"
    for prefix in ("", "r", "i")
    for operation in (
        "add",
        "and",
        "divmod",
        "floordiv",
        "lshift",
        "matmul",
        "mod",
        "mul",
        "or",
        "pow",
        "rshift",
        "sub",
        "truediv",
        "xor",
    )
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


def _callable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _call_name(call: ast.Call) -> str | None:
    return _callable_name(call.func)


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


def _nested_scopes(scope: ast.AST) -> tuple[ast.AST, ...]:
    nested_scope_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    scopes: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        if isinstance(node, nested_scope_types):
            scopes.append(node)
            continue
        pending.extend(ast.iter_child_nodes(node))
    return tuple(scopes)


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


def _score_aliases(
    nodes: tuple[ast.AST, ...],
    inherited: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    aliases = {name: set(fields) for name, fields in (inherited or {}).items()}
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


def _arithmetic_aliases(
    nodes: tuple[ast.AST, ...],
    inherited: set[str] | None = None,
) -> set[str]:
    aliases = set(inherited or ())
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if isinstance(node, ast.ImportFrom):
                for imported in node.names:
                    if imported.name not in ARITHMETIC_CALLS:
                        continue
                    target_name = imported.asname or imported.name
                    if target_name not in aliases:
                        aliases.add(target_name)
                        changed = True

            assignment = _assignment(node)
            if assignment is None:
                continue
            targets, value = assignment
            callable_name = _callable_name(value)
            if callable_name not in ARITHMETIC_CALLS and callable_name not in aliases:
                continue
            for target_name in _target_names(targets):
                if target_name not in aliases:
                    aliases.add(target_name)
                    changed = True
    return aliases


def _default_arithmetic_aliases(
    scope: ast.AST,
    inherited: set[str],
) -> set[str]:
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return set()

    positional = (*scope.args.posonlyargs, *scope.args.args)
    positional_with_defaults = positional[len(positional) - len(scope.args.defaults) :]
    parameter_defaults = [
        *zip(positional_with_defaults, scope.args.defaults, strict=True),
        *(
            (parameter, default)
            for parameter, default in zip(
                scope.args.kwonlyargs,
                scope.args.kw_defaults,
                strict=True,
            )
            if default is not None
        ),
    ]
    return {
        parameter.arg
        for parameter, default in parameter_defaults
        if (
            (callable_name := _callable_name(default)) in ARITHMETIC_CALLS
            or callable_name in inherited
        )
    }


def test_no_module_performs_arithmetic_combining_the_two_scores() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        def inspect_scope(
            scope: ast.AST,
            inherited_arithmetic: set[str],
            inherited_scores: dict[str, set[str]],
        ) -> None:
            nodes = _nodes_in_scope(scope)
            aliases = _score_aliases(nodes, inherited_scores)
            inherited_arithmetic_aliases = set(inherited_arithmetic)
            inherited_arithmetic_aliases.update(
                _default_arithmetic_aliases(scope, inherited_arithmetic)
            )
            arithmetic_aliases = _arithmetic_aliases(
                nodes,
                inherited_arithmetic_aliases,
            )
            for node in nodes:
                is_arithmetic = isinstance(node, ast.BinOp) or (
                    isinstance(node, ast.Call)
                    and (
                        _call_name(node) in ARITHMETIC_CALLS
                        or _call_name(node) in arithmetic_aliases
                    )
                )
                if not is_arithmetic:
                    continue
                if {"confidence", "evidence_quality"} <= _resolved_score_fields(node, aliases):
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

            for nested_scope in _nested_scopes(scope):
                inspect_scope(nested_scope, arithmetic_aliases, aliases)

        inspect_scope(tree, set(), {})

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


def test_score_arithmetic_gate_detects_score_aliases_captured_by_a_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "def make_blender(row):",
                "    pipeline = row.confidence",
                "    science = row.evidence_quality",
                "    def blend():",
                "        return pipeline + science",
                "    return blend",
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


def test_score_arithmetic_gate_detects_dunder_arithmetic_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "def blend(row):",
                "    return row.confidence.__add__(row.evidence_quality)",
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
        "\n".join(
            (
                "import operator",
                "",
                "def blend(row, combine=operator.add):",
                "    return combine(row.confidence, row.evidence_quality)",
            )
        ),
        "\n".join(
            (
                "import operator",
                "",
                "def make_blender(combine=operator.add):",
                "    def blend(row):",
                "        return combine(row.confidence, row.evidence_quality)",
                "    return blend",
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


def test_arithmetic_callable_aliases_do_not_leak_between_sibling_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "allowed.py").write_text(
        "\n".join(
            (
                "import operator",
                "",
                "def first(row):",
                "    combine = operator.add",
                "    return combine(row.confidence, 1)",
                "",
                "def second(row, combine):",
                "    return combine(row.confidence, row.evidence_quality)",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        test_no_module_performs_arithmetic_combining_the_two_scores.__globals__,
        "PACKAGE_ROOT",
        tmp_path,
    )

    test_no_module_performs_arithmetic_combining_the_two_scores()
