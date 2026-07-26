"""Command-line interface for AI-Researcher."""

import typer

app = typer.Typer(help="Research quantum computing and AI literature locally.")


@app.callback()
def main() -> None:
    """Research quantum computing and AI literature locally."""
