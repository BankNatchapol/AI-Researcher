import pytest

from ai_researcher.config import ConfigurationError, load_settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql://localhost/ai_researcher",
    "GROBID_URL": "http://localhost:8070",
    "LLM_BACKEND_DEFAULT": "codex",
    "CONTACT_EMAIL": "researcher@example.com",
}


def test_load_settings_reads_database_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)

    settings = load_settings()

    assert settings.database_url == REQUIRED_ENV["DATABASE_URL"]


def test_load_settings_raises_named_error_when_required_variable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_settings()
