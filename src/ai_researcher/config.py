"""Application settings sourced exclusively from environment variables."""

import os
from dataclasses import dataclass


class MissingConfigurationError(RuntimeError):
    """Raised when a required environment variable is absent."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for AI-Researcher."""

    database_url: str
    grobid_url: str
    llm_backend_default: str
    contact_email: str


def _required_environment_variable(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigurationError(f"Required environment variable {name} is missing")
    return value


def get_settings() -> Settings:
    """Read and return a fresh settings object from the current environment."""

    return Settings(
        database_url=_required_environment_variable("DATABASE_URL"),
        grobid_url=_required_environment_variable("GROBID_URL"),
        llm_backend_default=_required_environment_variable("LLM_BACKEND_DEFAULT"),
        contact_email=_required_environment_variable("CONTACT_EMAIL"),
    )
