"""Apply numbered SQL migrations transactionally and exactly once."""

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from ai_researcher.db import connect

MIGRATION_FILENAME = re.compile(r"^(?P<version>\d+)_(?P<label>[a-z0-9_]+)\.sql$")
MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")

CREATE_MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class MigrationDefinitionError(RuntimeError):
    """Raised when migration files do not form a valid ordered sequence."""


@dataclass(frozen=True, slots=True)
class Migration:
    """A numbered SQL migration loaded from disk."""

    version: int
    name: str
    path: Path


def discover_migrations(directory: Path = MIGRATIONS_DIRECTORY) -> tuple[Migration, ...]:
    """Return valid migration files in numeric order."""

    migrations: list[Migration] = []
    versions: set[int] = set()
    for path in directory.glob("*.sql"):
        match = MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationDefinitionError(f"Invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in versions:
            raise MigrationDefinitionError(f"Duplicate migration version: {version}")
        versions.add(version)
        migrations.append(Migration(version=version, name=path.stem, path=path))
    return tuple(sorted(migrations, key=lambda migration: migration.version))


def migrate() -> tuple[str, ...]:
    """Apply all pending migrations in one transaction and return their names."""

    migrations = discover_migrations()
    applied_now: list[str] = []

    with connect() as connection:
        connection.exec_driver_sql(CREATE_MIGRATION_TABLE)
        connection.exec_driver_sql("LOCK TABLE schema_migration IN EXCLUSIVE MODE")
        applied_versions = {
            row[0] for row in connection.exec_driver_sql("SELECT version FROM schema_migration")
        }

        for migration in migrations:
            if migration.version in applied_versions:
                continue
            connection.exec_driver_sql(migration.path.read_text(encoding="utf-8"))
            connection.execute(
                text(
                    """
                    INSERT INTO schema_migration (version, name)
                    VALUES (:version, :name)
                    """
                ),
                {"version": migration.version, "name": migration.name},
            )
            applied_now.append(migration.name)

    return tuple(applied_now)


__all__ = ["MigrationDefinitionError", "discover_migrations", "migrate"]
