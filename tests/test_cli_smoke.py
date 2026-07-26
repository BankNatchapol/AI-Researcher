"""Smoke tests for the installed command-line interface."""

import subprocess


def test_airesearch_help_exits_successfully() -> None:
    result = subprocess.run(
        ["airesearch", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout
