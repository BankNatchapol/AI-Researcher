"""Architecture guard for the single model-call boundary."""

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "forbidden",
    [
        "claude -p",
        "codex exec",
        "import litellm",
        "import openai",
        "import anthropic",
    ],
)
def test_model_calls_are_confined_to_the_llm_package(forbidden: str) -> None:
    package_root = Path(__file__).parents[1] / "src" / "ai_researcher"
    offenders = [
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*.py")
        if "llm" not in path.relative_to(package_root).parts
        and forbidden in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
