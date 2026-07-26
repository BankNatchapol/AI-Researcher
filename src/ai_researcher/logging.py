"""Structured logging for AI-Researcher — always to stderr."""

from __future__ import annotations

import logging
import sys

ROOT_LOGGER_NAME = "ai_researcher"
_CONFIGURED = False


def configure_logging(*, verbose: bool = False) -> None:
    """Configure the package logger to write to stderr.

    INFO is the default level; ``verbose=True`` enables DEBUG. stdout is left
    untouched so CLI command results stay pipeable.
    """

    global _CONFIGURED

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    handler: logging.Handler | None = None
    for existing in logger.handlers:
        if getattr(existing, "_ai_researcher_stderr", False):
            handler = existing
            break
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler._ai_researcher_stderr = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    else:
        # Rebind if stderr was replaced (e.g. CliRunner capture).
        handler.stream = sys.stderr  # type: ignore[attr-defined]

    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under ``ai_researcher``, configuring defaults once."""

    if not _CONFIGURED:
        configure_logging(verbose=False)
    if name is None or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


__all__ = ["ROOT_LOGGER_NAME", "configure_logging", "get_logger"]
