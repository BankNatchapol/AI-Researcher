"""Environment-driven application configuration."""

import os
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is unavailable."""


@dataclass(frozen=True)
class Settings:
    """Configuration required by the application."""

    database_url: str
    grobid_url: str
    llm_backend_default: str
    contact_email: str


def _required_environment_variable(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Required environment variable {name} is missing")
    return value


def load_settings() -> Settings:
    """Load a fresh settings object from process environment variables."""
    return Settings(
        database_url=_required_environment_variable("DATABASE_URL"),
        grobid_url=_required_environment_variable("GROBID_URL"),
        llm_backend_default=_required_environment_variable("LLM_BACKEND_DEFAULT"),
        contact_email=_required_environment_variable("CONTACT_EMAIL"),
    )
