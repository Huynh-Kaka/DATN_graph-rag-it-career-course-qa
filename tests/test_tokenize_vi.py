"""B-03 — Vietnamese tokenizer (underthesea + regex fallback)."""

from unittest.mock import MagicMock

import pytest

import app.rag.retriever as retriever_mod
from app.rag.retriever import _tokenize, _tokenize_regex, _tokenize_with_underthesea


def test_tokenize_underthesea_compound_word(monkeypatch):
    """Có underthesea: 'máy tính' → một token ghép máy_tính (sau unidecode: may_tinh)."""
    monkeypatch.setattr(retriever_mod, "_check_underthesea", lambda: True)
    monkeypatch.setattr(
        retriever_mod,
        "_tokenize_with_underthesea",
        lambda text: ["học", "máy_tính"],
    )
    tokens = _tokenize("Học máy tính")
    assert tokens == ["hoc", "may_tinh"]


def test_tokenize_fallback_without_underthesea(monkeypatch):
    """Không có underthesea: tách theo khoảng trắng / regex."""
    monkeypatch.setattr(retriever_mod, "_check_underthesea", lambda: False)
    tokens = _tokenize("Học máy tính")
    assert tokens == ["hoc", "may", "tinh"]


def test_tokenize_with_underthesea_mock_word_tokenize(monkeypatch):
    def fake_word_tokenize(text: str, format: str = "text") -> str:
        assert format == "text"
        return "Học máy_tính"

    fake_module = MagicMock(word_tokenize=fake_word_tokenize)
    monkeypatch.setitem(__import__("sys").modules, "underthesea", fake_module)
    tokens = _tokenize_with_underthesea("Học máy tính")
    assert tokens == ["học", "máy_tính"]


def test_tokenize_regex_fallback_splits_on_whitespace():
    tokens = _tokenize_regex("hoc may tinh")
    assert tokens == ["hoc", "may", "tinh"]


@pytest.mark.skipif(
    not retriever_mod._check_underthesea(),
    reason="underthesea not installed",
)
def test_tokenize_integration_when_underthesea_installed():
    tokens = _tokenize("Học máy tính")
    assert "may_tinh" in tokens or "may" in tokens
