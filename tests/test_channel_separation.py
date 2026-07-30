"""Mechanical build gates for evidence/discourse channel separation."""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Iterable
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

# The two named entry points that persist claim_score rows one call of
# indirection away from the literal insert()/update() statement
# (PostgresQualityStore.save_quality in scoring/quality.py, and
# PostgresConfidenceStore.save_confidence in scoring/confidence.py, which is
# a pure pass-through to save_quality). Recognized by literal name only —
# this does NOT trace calls through score_scope_confidence or any aliased/
# injected callable (e.g. monitor/sweep.py's score_fn parameter, assigned
# from `import ... as` and threaded through a function argument). Tracing
# that kind of indirection is the same unbounded chase that took 8 rebuild
# rounds on issue #48's AC4 gate (see test_score_separation.py's docstring
# on test_no_module_performs_arithmetic_combining_the_two_scores) before
# that gate's real guarantee was moved to a behavioral test instead. The
# complete guarantee for indirect callers here is
# test_score_input_dataclasses_carry_no_discourse_fields below, not this.
CLAIM_SCORE_WRITER_FUNCTION_NAMES = frozenset({"save_quality", "save_confidence"})


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


def _is_discourse_package_module(module: str) -> bool:
    """True only for the actual ``ai_researcher.discourse`` package, not lookalikes.

    A plain substring check on ``.discourse`` also matches
    ``ai_researcher.db.models.discourse_item``/``discourse_mention`` — DB table
    objects legitimately imported by ``digest/build.py`` and
    ``monitor/changes.py``, which have nothing to do with the discourse
    polling package. Strip the ``ai_researcher.`` prefix (if present) and
    require an exact ``discourse`` segment or ``discourse.`` sub-package.
    """

    candidate = module.removeprefix("ai_researcher.")
    return candidate == "discourse" or candidate.startswith("discourse.")


def _imports_discourse(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        for module in _imported_modules(node):
            if _is_discourse_package_module(module):
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
        if name in CLAIM_SCORE_WRITER_FUNCTION_NAMES:
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
                if _is_discourse_package_module(module):
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


def test_channel_gate_does_not_flag_discourse_named_db_model_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """digest/build.py and monitor/changes.py import discourse_item/discourse_mention
    (DB table objects) from db.models, and separately, legitimately write
    claim_score elsewhere. Neither fact should trip a violation — this is the
    false positive the old blanket ".discourse" substring check risked once
    claim_score write-site detection was broadened.
    """

    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "from ai_researcher.db.models import claim_score",
                "from ai_researcher.db.models import discourse_item, discourse_mention",
                "from sqlalchemy import insert",
                "",
                "def record_score(confidence, evidence_quality):",
                "    return insert(claim_score).values(",
                "        claim_id=1,",
                "        confidence=confidence,",
                "        evidence_quality=evidence_quality,",
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
    test_no_discourse_value_written_to_claim_score()  # must not raise


# ─────────────────────────── structural guarantees ───────────────────────────
# Unlike the AST scans above, these two checks are complete for what they
# cover — not best-effort. They can't be defeated by a new alias or
# call-indirection pattern, because they don't trace source-text patterns at
# all: one introspects a fixed, enumerable dataclass field set, the other
# scans exactly one named function body (no whole-package search needed,
# since there is exactly one query that populates confidence-scoring
# dataclasses from the database).


def _discourse_dataclass_field_violations(classes: Iterable[type]) -> list[str]:
    """Complete guarantee: these are frozen, slotted dataclasses with a fixed
    field set. A field cannot be secretly added to one without changing its
    visible class declaration, so dataclasses.fields() introspection is
    decidable in a way source-text scanning is not.
    """

    violations: list[str] = []
    for cls in classes:
        for field in dataclasses.fields(cls):
            if field.name in DISCOURSE_VALUE_NAMES:
                violations.append(f"{cls.__name__}.{field.name}")
    return violations


def test_score_input_dataclasses_carry_no_discourse_fields() -> None:
    """The only inputs score_confidence()/score_quality() can ever read are
    the fields of these four dataclasses — if none of those fields are
    discourse-flavored, no discourse value can reach either score, no matter
    how it's called or through how many layers of indirection.
    """

    from ai_researcher.scoring.confidence import ConfidenceClaim, SupportingNode
    from ai_researcher.scoring.quality import QualityClaim, QualityEvidence

    violations = _discourse_dataclass_field_violations(
        (ConfidenceClaim, SupportingNode, QualityClaim, QualityEvidence)
    )
    assert violations == [], "discourse-flavored field on a score input dataclass: " + ", ".join(
        violations
    )


def test_score_input_dataclass_gate_detects_discourse_field() -> None:
    @dataclasses.dataclass(frozen=True, slots=True)
    class Probe:
        id: int
        upvotes: int

    assert _discourse_dataclass_field_violations((Probe,)) == ["Probe.upvotes"]


CONFIDENCE_MODULE = PACKAGE_ROOT / "scoring" / "confidence.py"
CONFIDENCE_LOADER_CLASS = "PostgresConfidenceStore"
CONFIDENCE_LOADER_METHOD = "load_unscored_claims"
DISCOURSE_TABLE_NAMES = DISCOURSE_VALUE_NAMES | frozenset({"discourse_source"})


def _find_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(
        f"{class_name}.{method_name} not found — this loader check is stale"
        " and needs to be repointed at wherever ConfidenceClaim is now built"
        " from the database"
    )


def test_confidence_loader_does_not_reference_discourse_tables() -> None:
    """Narrow, exact check on the single function that populates
    ConfidenceClaim/QualityEvidence from the database. Unlike the whole-
    package write-site scan, this only has to inspect one named function
    body to be complete, so no alias/closure tracing is needed.
    """

    tree = ast.parse(
        CONFIDENCE_MODULE.read_text(encoding="utf-8"),
        filename=str(CONFIDENCE_MODULE),
    )
    method = _find_method(tree, CONFIDENCE_LOADER_CLASS, CONFIDENCE_LOADER_METHOD)
    referenced = _names_in(method) & DISCOURSE_TABLE_NAMES
    assert referenced == set(), f"loader references discourse tables: {sorted(referenced)}"


def test_confidence_loader_gate_detects_discourse_table_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = tmp_path / "confidence.py"
    fake_module.write_text(
        "\n".join(
            (
                "class PostgresConfidenceStore:",
                "    def load_unscored_claims(self, scope_name):",
                "        return discourse_mention.c.id",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        test_confidence_loader_does_not_reference_discourse_tables.__globals__,
        "CONFIDENCE_MODULE",
        fake_module,
    )
    with pytest.raises(AssertionError, match="loader references discourse tables"):
        test_confidence_loader_does_not_reference_discourse_tables()


def test_confidence_loader_gate_fails_loudly_if_loader_method_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        test_confidence_loader_does_not_reference_discourse_tables.__globals__,
        "CONFIDENCE_LOADER_METHOD",
        "this_method_does_not_exist",
    )
    with pytest.raises(AssertionError, match="loader check is stale"):
        test_confidence_loader_does_not_reference_discourse_tables()


def test_channel_gate_detects_discourse_value_passed_directly_to_save_confidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct call to save_confidence/save_quality is a write site too.

    This is the exact shape of the confirmed bypass: neither of these two
    functions is a literal insert()/update() call, so before this test they
    were completely invisible to _claim_score_write_sites — a file could
    import discourse and call save_confidence(confidence=reddit_upvotes,
    ...) directly and trip nothing.
    """

    (tmp_path / "violation.py").write_text(
        "\n".join(
            (
                "from ai_researcher import discourse",
                "",
                "def leak(store, upvotes):",
                "    return store.save_confidence(",
                "        claim_id=1,",
                "        confidence=upvotes,",
                "        quality=None,",
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
