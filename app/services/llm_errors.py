from __future__ import annotations

from app.intent.templates import (
    GENERATOR_NETWORK_MESSAGE,
    GENERATOR_OVERLOAD_MESSAGE,
    GENERATOR_UNKNOWN_ERROR_MESSAGE,
)

_OVERLOAD_MARKERS = (
    "503",
    "429",
    "502",
    "504",
    "unavailable",
    "resource_exhausted",
    "high demand",
    "overloaded",
    "quota",
)

_NETWORK_MARKERS = (
    "timeout",
    "timed out",
    "connection refused",
    "connection error",
    "connecterror",
    "network",
    "connection reset",
    "name or service not known",
    "failed to establish",
)


def _detail(exc: BaseException) -> str:
    return str(exc).lower()


def is_transient_llm_error(exc: BaseException) -> bool:
    """Lỗi tạm thời — có thể retry (503, timeout, connection)."""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            return True
    except ImportError:
        pass
    detail = _detail(exc)
    return any(marker in detail for marker in (*_OVERLOAD_MARKERS, *_NETWORK_MARKERS))


def is_quota_or_overload_error(exc: BaseException) -> bool:
    detail = _detail(exc)
    return any(marker in detail for marker in _OVERLOAD_MARKERS)


def is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            return True
    except ImportError:
        pass
    detail = _detail(exc)
    return any(marker in detail for marker in _NETWORK_MARKERS)


def normalize_llm_error_message(exc: BaseException) -> str:
    """Chuẩn hóa exception LLM thành message tiếng Việt, không lộ chi tiết kỹ thuật."""
    if is_quota_or_overload_error(exc):
        return GENERATOR_OVERLOAD_MESSAGE
    if is_network_error(exc):
        return GENERATOR_NETWORK_MESSAGE
    return GENERATOR_UNKNOWN_ERROR_MESSAGE
