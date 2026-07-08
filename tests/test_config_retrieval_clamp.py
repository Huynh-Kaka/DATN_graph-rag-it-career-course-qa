"""G1 — RETRIEVAL_RRF_K / POOL_SIZE clamp."""

from __future__ import annotations

import importlib

import pytest


def _reload_config(monkeypatch, **env: str):
    for key, val in env.items():
        monkeypatch.setenv(key, val)
    import app.core.config as cfg

    importlib.reload(cfg)
    return cfg.settings


def test_rrf_k_clamped_high(monkeypatch):
    s = _reload_config(monkeypatch, RETRIEVAL_RRF_K="999")
    assert s.retrieval_rrf_k == 80


def test_rrf_k_clamped_low(monkeypatch):
    s = _reload_config(monkeypatch, RETRIEVAL_RRF_K="5")
    assert s.retrieval_rrf_k == 20


def test_rrf_pool_clamped(monkeypatch):
    s = _reload_config(monkeypatch, RETRIEVAL_RRF_POOL_SIZE="10")
    assert s.retrieval_rrf_pool_size == 30
