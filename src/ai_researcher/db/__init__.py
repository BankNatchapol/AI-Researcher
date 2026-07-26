"""PostgreSQL connection handling for AI-Researcher."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import make_url

from ai_researcher.config import get_settings


def get_engine() -> Engine:
    """Build an engine for the configured PostgreSQL database."""

    database_url = make_url(get_settings().database_url)
    if database_url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use PostgreSQL")
    return create_engine(database_url.set(drivername="postgresql+pg8000"))


@contextmanager
def connect() -> Iterator[Connection]:
    """Open a transaction-scoped connection using the configured database URL."""

    engine = get_engine()
    try:
        with engine.begin() as connection:
            yield connection
    finally:
        engine.dispose()


__all__ = ["connect", "get_engine"]
