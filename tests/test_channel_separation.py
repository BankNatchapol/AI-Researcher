"""Mechanical build gates for evidence/discourse channel separation."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Generic, Protocol, get_origin

import pytest

from ai_researcher.discourse.base import DiscourseSource
from ai_researcher.sources.base import EvidenceSource

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "ai_researcher"

# Names that signal community-attention / discourse-derived values.
DISCOURSE_VALUE_NAMES = frozenset(
    {
        "attention",
        "discourse",
        "discourse_item",
        "discourse_mention",
        "discourse_score",
        "hn_points",
        "num_comments",
        "reddit_score",
        "scite",
        "scites",
        "upvote",
        "upvotes",
    }
)

# claim_score columns that must never receive discourse-derived inputs.
CLAIM_SCORE_VALUE_KEYS = frozenset({"confidence", "evidence_quality"})


def _imported_modules(node: ast.AST) -> list[str]:
    modules: list[str] = []
    if isinstance(node, ast.Import):
        modules = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        base_module = node.module or ""
        modules = [
            base_module,
            *(f"{base_module}.{alias.name}" if base_module else alias.name for alias in node.names),
        ]
    return modules


def _imports_discourse(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        for module in _imported_modules(node):
            if module == "discourse" or ".discourse" in module:
                return True
    return False


def _callable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _names_in(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for descendant in ast.walk(node):
        if isinstance(descendant, ast.Name):
            names.add(descendant.id)
        elif isinstance(descendant, ast.Attribute):
            names.add(descendant.attr)
        elif (
            isinstance(descendant, ast.Subscript)
            and isinstance(descendant.slice, ast.Constant)
            and isinstance(descendant.slice.value, str)
        ):
            names.add(descendant.slice.value)
        elif isinstance(descendant, ast.keyword) and descendant.arg:
            names.add(descendant.arg)
        elif isinstance(descendant, ast.Call) and _callable_name(descendant.func) in {
            "get",
            "getattr",
        }:
            for arg in descendant.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.add(arg.value)
    return names


def _is_claim_score_target(node: ast.AST) -> bool:
    """True when ``node`` refers to the claim_score table or its insert helper."""

    if isinstance(node, ast.Name) and node.id == "claim_score":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "claim_score":
        return True
    return False


def _claim_score_write_sites(tree: ast.AST) -> list[ast.Call]:
    sites: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callable_name(node.func)
        if name in {"insert", "update"} and node.args and _is_claim_score_target(node.args[0]):
            sites.append(node)
            continue
        # insert(claim_score).values(...)  — values is Attribute of Call
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "values"
            and isinstance(node.func.value, ast.Call)
        ):
            inner = node.func.value
            inner_name = _callable_name(inner.func)
            if (
                inner_name in {"insert", "update"}
                and inner.args
                and _is_claim_score_target(inner.args[0])
            ):
                sites.append(node)
    return sites


def test_discourse_and_evidence_share_no_base_class() -> None:
    # Protocol / Generic are typing markers every Protocol shares — allowed.
    # A custom ABC or shared Source base is not.
    ignored = {object, Protocol, Generic}
    discourse_bases = {
        base
        for base in DiscourseSource.__mro__
        if base not in ignored
        and base is not DiscourseSource
        and get_origin(base) is not Protocol
        and getattr(base, "__name__", "") != "Protocol"
    }
    evidence_bases = {
        base
        for base in EvidenceSource.__mro__
        if base not in ignored
        and base is not EvidenceSource
        and get_origin(base) is not Protocol
        and getattr(base, "__name__", "") != "Protocol"
    }
    shared = discourse_bases & evidence_bases
    assert shared == set(), f"protocols share base class(es): {shared}"
    assert DiscourseSource is not EvidenceSource
    assert EvidenceSource not in DiscourseSource.__mro__
    assert DiscourseSource not in EvidenceSource.__mro__
    # Distinct method sets — structural separation beyond inheritance.
    discourse_methods = {"poll", "link_targets"}
    evidence_methods = {"search", "fetch_metadata", "pdf_url"}
    discourse_members = {name for name in DiscourseSource.__dict__ if not name.startswith("_")}
    evidence_members = {name for name in EvidenceSource.__dict__ if not name.startswith("_")}
    assert discourse_methods <= discourse_members
    assert evidence_methods <= evidence_members
    assert discourse_methods.isdisjoint(evidence_members)
    assert evidence_methods.isdisjoint(discourse_members)


def test_scoring_package_does_not_import_discourse() -> None:
    violations: list[str] = []
    scoring_root = PACKAGE_ROOT / "scoring"
    for path in sorted(scoring_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if module == "discourse" or ".discourse" in module:
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")
    assert violations == [], "scoring imports discourse: " + ", ".join(violations)


def test_no_discourse_value_written_to_claim_score() -> None:
    """No insert/update of claim_score may feed discourse-derived names into scores."""

    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imports_discourse = _imports_discourse(tree)
        for site in _claim_score_write_sites(tree):
            names = _names_in(site)
            discourse_names = names & DISCOURSE_VALUE_NAMES
            if discourse_names:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{site.lineno} uses {sorted(discourse_names)}"
                )
            if imports_discourse:
                # A module that imports discourse must not write claim_score at all.
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{site.lineno}"
                    " writes claim_score while importing discourse"
                )
            # Values keyed into confidence / evidence_quality must not reference
            # discourse identifiers (even without an import, e.g. via getattr).
            for keyword in site.keywords:
                if keyword.arg in CLAIM_SCORE_VALUE_KEYS:
                    bad = _names_in(keyword.value) & DISCOURSE_VALUE_NAMES
                    if bad:
                        violations.append(
                            f"{path.relative_to(PACKAGE_ROOT)}:{site.lineno}"
                            f" {keyword.arg} from {sorted(bad)}"
                        )

    assert violations == [], "discourse value reaches claim_score: " + "; ".join(violations)


def test_channel_gate_detects_scoring_discourse_import(
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


def test_channel_gate_detects_discourse_into_claim_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "from ai_researcher import discourse",
                "from sqlalchemy import insert",
                "from ai_researcher.db.models import claim_score",
                "",
                "def persist(upvotes):",
                "    return insert(claim_score).values(",
                "        claim_id=1,",
                "        confidence=upvotes,",
                "        evidence_quality=0.5,",
                "    )",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        test_no_discourse_value_written_to_claim_score.__globals__,
        "PACKAGE_ROOT",
        tmp_path,
    )
    with pytest.raises(AssertionError, match="discourse value reaches claim_score"):
        test_no_discourse_value_written_to_claim_score()
