"""Phần B: retry tự động trước khi báo lỗi cho người dùng."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.intent.templates import GENERATOR_OVERLOAD_MESSAGE
from app.services.generator_backend import generate_reply


class _Gemini503Error(Exception):
    def __str__(self) -> str:
        return (
            "503 UNAVAILABLE. {'error': {'code': 503, "
            "'message': 'high demand', 'status': 'UNAVAILABLE'}}"
        )


def test_retry_succeeds_on_third_attempt(monkeypatch):
    monkeypatch.setenv("GENERATOR_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GENERATOR_RETRY_BACKOFF_SECONDS", "0")
    from app.core import config

    config.settings = config.Settings()

    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = [
        _Gemini503Error(),
        _Gemini503Error(),
        "ok after retry",
    ]
    local = MagicMock()
    local.available = False

    text, backend, is_error = generate_reply(
        intent="pathfinding",
        system_prompt="sys",
        user_prompt="user",
        gemini=gemini,
        local=local,
    )

    assert is_error is False
    assert text == "ok after retry"
    assert backend == "gemini"
    assert gemini.generate.call_count == 3


def test_retry_exhausted_returns_normalized_error(monkeypatch):
    monkeypatch.setenv("GENERATOR_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GENERATOR_RETRY_BACKOFF_SECONDS", "0")
    from app.core import config

    config.settings = config.Settings()

    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = _Gemini503Error()
    local = MagicMock()
    local.available = False

    text, backend, is_error = generate_reply(
        intent="pathfinding",
        system_prompt="sys",
        user_prompt="user",
        gemini=gemini,
        local=local,
    )

    assert is_error is True
    assert text == GENERATOR_OVERLOAD_MESSAGE
    assert backend == "gemini_error"
    assert gemini.generate.call_count == 3


def test_non_transient_error_not_retried(monkeypatch):
    monkeypatch.setenv("GENERATOR_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GENERATOR_RETRY_BACKOFF_SECONDS", "0")
    from app.core import config

    config.settings = config.Settings()

    class BadRequestError(Exception):
        def __str__(self) -> str:
            return "400 INVALID_ARGUMENT bad input"

    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = BadRequestError()
    local = MagicMock()
    local.available = False

    text, backend, is_error = generate_reply(
        intent="pathfinding",
        system_prompt="sys",
        user_prompt="user",
        gemini=gemini,
        local=local,
    )

    assert is_error is True
    assert gemini.generate.call_count == 1
