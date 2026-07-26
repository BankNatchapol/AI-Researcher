"""Command-line interface for AI-Researcher."""

from datetime import date

import typer

app = typer.Typer(help="Research quantum computing and AI literature locally.")
db_app = typer.Typer(help="Manage the local PostgreSQL database.")
scope_app = typer.Typer(help="Create and inspect reproducible research scopes.")
app.add_typer(db_app, name="db")
app.add_typer(scope_app, name="scope")


@app.callback()
def main() -> None:
    """Research quantum computing and AI literature locally."""


@db_app.command("migrate")
def migrate_database() -> None:
    """Apply pending database migrations."""

    from ai_researcher.db.migrate import migrate

    applied = migrate()
    if not applied:
        typer.echo("Database already up to date.")
        return
    for migration_name in applied:
        typer.echo(f"Applied migration {migration_name}.")


@scope_app.command("new")
def new_scope(
    name: str,
    description: str | None = typer.Option(None, help="Broad research topic."),
    category: list[str] = typer.Option(
        [],
        "--category",
        "-c",
        help="arXiv category to include; repeat for multiple categories.",
    ),
    date_from: str | None = typer.Option(None, help="Earliest publication date (YYYY-MM-DD)."),
    date_to: str | None = typer.Option(None, help="Latest publication date (YYYY-MM-DD)."),
    per_source_limit: int = typer.Option(100, min=1, help="Trial result cap for each source."),
) -> None:
    """Run a narrowing dialogue and persist a new scope."""

    from ai_researcher.scoping import ScopeDefinition, dialogue, store

    broad_topic = description.strip() if description else name.replace("-", " ")
    try:
        definition = ScopeDefinition(
            name=name,
            description=broad_topic,
            include_terms=(broad_topic,),
            exclude_terms=(),
            categories=tuple(_split_values(category)),
            date_from=_parse_date(date_from, "--date-from"),
            date_to=_parse_date(date_to, "--date-to"),
            per_source_limit=per_source_limit,
        )
        narrowed = dialogue.run_dialogue(
            definition,
            confirm=lambda prompt: typer.confirm(prompt, default=False),
            emit=typer.echo,
        )
        store.save_scope(narrowed)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Saved scope '{name}'.")


@scope_app.command("show")
def show_scope(name: str) -> None:
    """Print a scope's full definition and current corpus estimate."""

    from ai_researcher.scoping import estimate, store

    definition = store.load_scope(name)
    if definition is None:
        raise typer.BadParameter(f"Unknown scope: {name}")
    estimated_size = estimate.estimate_scope(definition)
    typer.echo(f"Name: {definition.name}")
    typer.echo(f"Description: {definition.description}")
    typer.echo(f"Include terms: {_display_values(definition.include_terms)}")
    typer.echo(f"Exclude terms: {_display_values(definition.exclude_terms)}")
    typer.echo(f"arXiv categories: {_display_values(definition.categories)}")
    typer.echo(
        "Date range: "
        f"{definition.date_from.isoformat() if definition.date_from else '(any)'} to "
        f"{definition.date_to.isoformat() if definition.date_to else '(any)'}"
    )
    typer.echo(f"Per-source limit: {definition.per_source_limit}")
    typer.echo(f"Estimated corpus size: {estimated_size}")


@scope_app.command("list")
def list_scopes() -> None:
    """Print every saved scope and its current corpus estimate."""

    from ai_researcher.scoping import estimate, store

    definitions = store.list_scopes()
    if not definitions:
        typer.echo("No scopes found.")
        return
    typer.echo("Name\tEstimated corpus size")
    for definition in definitions:
        typer.echo(f"{definition.name}\t{estimate.estimate_scope(definition)}")


@app.command("ingest")
def ingest_scope(scope_name: str = typer.Argument(..., metavar="SCOPE")) -> None:
    """Run discover → acquire → parse for a saved scope."""

    from ai_researcher.ingest import pipeline

    try:
        result = pipeline.run_ingest(scope_name)
    except pipeline.UnknownScopeError as error:
        raise typer.BadParameter(str(error)) from error
    except pipeline.CorpusCeilingExceededError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Ingest {result.state}: found {result.papers_found}, "
        f"newly parsed {result.papers_newly_parsed}."
    )


def _parse_date(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{option_name} must use YYYY-MM-DD") from error


def _split_values(values: list[str]) -> list[str]:
    return [item.strip() for value in values for item in value.split(",") if item.strip()]


def _display_values(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "(none)"
