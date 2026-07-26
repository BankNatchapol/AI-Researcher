"""Command-line interface for AI-Researcher."""

import typer

app = typer.Typer(help="Research quantum computing and AI literature locally.")
db_app = typer.Typer(help="Manage the local PostgreSQL database.")
app.add_typer(db_app, name="db")


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
