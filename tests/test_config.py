"""Tests for environment-driven application settings."""

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_config_module() -> ModuleType:
    assert importlib.util.find_spec("ai_researcher.config") is not None
    return importlib.import_module("ai_researcher.config")


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")


def test_settings_read_database_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    config = _load_config_module()

    settings = config.get_settings()

    assert settings.database_url == "postgresql://localhost/research"


def test_missing_required_variable_raises_named_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")
    config = _load_config_module()

    with pytest.raises(config.MissingConfigurationError, match="DATABASE_URL"):
        config.get_settings()


def test_settings_read_pdf_storage_directory_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("STORAGE_DIR", "/tmp/ai-researcher-papers")
    config = _load_config_module()

    settings = config.get_settings()

    assert settings.storage_dir == Path("/tmp/ai-researcher-papers")


def test_shortlist_backend_defaults_to_pageindex_and_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    config = _load_config_module()

    monkeypatch.delenv("SHORTLIST_BACKEND", raising=False)
    assert config.get_settings().shortlist_backend == "pageindex"

    monkeypatch.setenv("SHORTLIST_BACKEND", "postgres_fts")
    assert config.get_settings().shortlist_backend == "postgres_fts"
