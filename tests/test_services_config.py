"""Contract tests for the local PostgreSQL and GROBID services."""

from pathlib import Path

import pytest

from ai_researcher.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://tester:secret@db.example/research")
    monkeypatch.setenv("GROBID_URL", "http://grobid.example:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")


def test_service_urls_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_environment(monkeypatch)

    settings = get_settings()

    assert settings.database_url == "postgresql://tester:secret@db.example/research"
    assert settings.grobid_url == "http://grobid.example:8070"


def test_compose_declares_native_healthy_backing_services() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text()

    assert "postgres:16" in compose
    assert "lfoppiano/grobid:0.9.0-crf" in compose
    assert compose.count("platform: linux/arm64") == 2
    assert compose.count("healthcheck:") == 2
    assert "postgres_data:" in compose


def test_postgres_password_must_come_from_local_environment() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text()
    example_environment = (REPO_ROOT / ".env.example").read_text()

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "POSTGRES_PASSWORD:-" not in compose
    assert "POSTGRES_PASSWORD=\n" in example_environment
    assert "postgres:postgres@" not in example_environment
