from unittest.mock import MagicMock

from app.services.generator_backend import generate_reply, resolve_backend_for_intent


def test_slot_fill_always_gemini(monkeypatch):
    monkeypatch.setenv("USE_LOCAL_GENERATOR", "1")
    monkeypatch.setenv("GENERATOR_BACKEND", "auto")
    from app.core import config

    config.settings = config.Settings()
    assert resolve_backend_for_intent("slot_fill") == "gemini"


def test_generate_reply_uses_gemini_when_mode_gemini(monkeypatch):
    monkeypatch.setenv("GENERATOR_BACKEND", "gemini")
    monkeypatch.setenv("USE_LOCAL_GENERATOR", "1")
    from app.core import config

    config.settings = config.Settings()

    gemini = MagicMock()
    gemini.available = True
    gemini.generate.return_value = "from gemini"
    local = MagicMock()
    local.available = True

    text, backend, is_error = generate_reply(
        intent="pathfinding",
        system_prompt="sys",
        user_prompt="user",
        gemini=gemini,
        local=local,
    )
    assert text == "from gemini"
    assert backend == "gemini"
    assert is_error is False
    local.generate.assert_not_called()
