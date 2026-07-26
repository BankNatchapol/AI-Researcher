from typer.testing import CliRunner

from ai_researcher.cli import app


def test_help_prints_usage() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
