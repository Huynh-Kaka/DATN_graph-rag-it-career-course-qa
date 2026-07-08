from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core import config
from app.services.chat_completion_gateway import ChatCompletionGateway


def _apply_settings(monkeypatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    cfg = config.Settings()
    if "CHATBOT_LLM_MODE" in env:
        cfg.chatbot_llm_mode = int(env["CHATBOT_LLM_MODE"])
    if "CHATBOT_LOCAL_BASE_URL" in env:
        cfg.chatbot_local_base_url = env["CHATBOT_LOCAL_BASE_URL"]
    if "GEMINI_API_KEY" in env:
        cfg.gemini_api_key = env["GEMINI_API_KEY"]
    monkeypatch.setattr(config, "settings", cfg)


def test_prefers_local_when_configured(monkeypatch):
    _apply_settings(
        monkeypatch,
        CHATBOT_LLM_MODE="1",
        CHATBOT_LOCAL_BASE_URL="http://localhost:8081/v1",
        GEMINI_API_KEY="test-key",
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="local reply"))]
    )
    gw = ChatCompletionGateway.__new__(ChatCompletionGateway)
    gw._openai = mock_client
    gw._gemini = None
    assert gw.prefer_local is True

    text, backend = gw.generate_text(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.7,
        max_output_tokens=100,
        primary_model="gemini-2.5-flash-lite",
        fallback_models="",
        )
    assert text == "local reply"
    assert backend == "chatbot_local"
    mock_client.chat.completions.create.assert_called_once()


def test_falls_back_to_gemini_when_local_fails(monkeypatch):
    _apply_settings(
        monkeypatch,
        CHATBOT_LLM_MODE="1",
        CHATBOT_LOCAL_BASE_URL="http://localhost:8081/v1",
        GEMINI_API_KEY="test-key",
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("down")
    gw = ChatCompletionGateway.__new__(ChatCompletionGateway)
    gw._openai = mock_client
    gw._gemini = None

    with patch.object(gw, "_gemini_generate_text", return_value="gemini reply") as gem:
        text, backend = gw.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.7,
            max_output_tokens=100,
            primary_model="gemini-2.5-flash-lite",
            fallback_models="",
        )
    assert text == "gemini reply"
    assert backend == "gemini"
    gem.assert_called_once()


def test_gemini_only_when_mode_2_even_with_local_url(monkeypatch):
    _apply_settings(
        monkeypatch,
        CHATBOT_LLM_MODE="2",
        CHATBOT_LOCAL_BASE_URL="http://localhost:8081/v1",
        GEMINI_API_KEY="test-key",
    )

    gw = ChatCompletionGateway()
    assert gw.prefer_local is False
    assert gw.local_configured is False
    with patch.object(gw, "_gemini_generate_text", return_value="only gemini") as gem:
        text, backend = gw.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.7,
            max_output_tokens=100,
            primary_model="gemini-2.5-flash-lite",
            fallback_models="",
        )
    assert text == "only gemini"
    assert backend == "gemini"
    gem.assert_called_once()


def test_gemini_only_when_local_not_configured(monkeypatch):
    _apply_settings(
        monkeypatch,
        CHATBOT_LLM_MODE="1",
        CHATBOT_LOCAL_BASE_URL="",
        GEMINI_API_KEY="test-key",
    )

    gw = ChatCompletionGateway()
    assert gw.local_configured is False
    with patch.object(gw, "_gemini_generate_text", return_value="only gemini") as gem:
        text, backend = gw.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.7,
            max_output_tokens=100,
            primary_model="gemini-2.5-flash-lite",
            fallback_models="",
        )
    assert text == "only gemini"
    assert backend == "gemini"
    gem.assert_called_once()


def test_raises_when_no_llm_configured():
    gw = ChatCompletionGateway.__new__(ChatCompletionGateway)
    gw._openai = None
    gw._gemini = None
    assert gw.available is False
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gw.generate_text(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.7,
            max_output_tokens=100,
            primary_model="gemini-2.5-flash-lite",
            fallback_models="",
        )
