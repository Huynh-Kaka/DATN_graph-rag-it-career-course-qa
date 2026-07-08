from datetime import datetime, timezone

from app.core.config import _env_datetime


def test_env_datetime_parses_z_suffix(monkeypatch):
    monkeypatch.setenv("SESSION_FILTER_AFTER", "2025-06-01T00:00:00Z")
    dt = _env_datetime("SESSION_FILTER_AFTER")
    assert dt == datetime(2025, 6, 1, tzinfo=timezone.utc)


def test_env_datetime_empty_returns_none(monkeypatch):
    monkeypatch.delenv("SESSION_FILTER_AFTER", raising=False)
    assert _env_datetime("SESSION_FILTER_AFTER") is None


def test_env_datetime_naive_assumes_utc(monkeypatch):
    monkeypatch.setenv("SESSION_FILTER_AFTER", "2025-06-01T00:00:00")
    dt = _env_datetime("SESSION_FILTER_AFTER")
    assert dt == datetime(2025, 6, 1, tzinfo=timezone.utc)
