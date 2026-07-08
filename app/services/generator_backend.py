from __future__ import annotations

import logging
import time
from enum import Enum

from app.core.config import settings
from app.services.chat_completion_gateway import ChatCompletionGateway
from app.services.gemini_generator_client import GeminiGeneratorClient
from app.services.llm_errors import is_transient_llm_error, normalize_llm_error_message
from app.services.local_generator_client import LocalGeneratorClient

logger = logging.getLogger(__name__)


class GeneratorIntent(str, Enum):
    SLOT_FILL = "slot_fill"
    PATHFINDING = "pathfinding"
    COURSE_REC = "course_rec"


def resolve_backend_for_intent(intent: str) -> str:
    """
    Chọn backend sinh câu trả lời theo phân tích kiến trúc:
    - slot_fill: luôn Gemini (JSON/ngắn, chưa fine-tune local)
    - pathfinding / course_rec: local nếu bật và Ollama OK, ngược lại Gemini
    """
    mode = (settings.generator_backend or "auto").lower()
    if intent == GeneratorIntent.SLOT_FILL.value:
        return "gemini"

    if mode == "gemini":
        return "gemini"
    if mode == "local":
        return "local"

    # auto: theo USE_LOCAL_GENERATOR
    if settings.use_local_generator:
        return "local"
    return "gemini"


def _error_result(exc: Exception, backend_label: str) -> tuple[str, str, bool]:
    logger.warning("Generator %s failed: %s", backend_label, exc)
    return normalize_llm_error_message(exc), f"{backend_label}_error", True


def _call_with_retry(call_fn, *, backend_label: str) -> tuple[str, str, bool]:
    """Gọi LLM với retry exponential backoff cho lỗi tạm thời (503, timeout, ...)."""
    max_retries = max(0, settings.generator_retry_max_attempts)
    backoff = settings.generator_retry_backoff_seconds
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return call_fn(), backend_label, False
        except Exception as exc:
            last_exc = exc
            if not is_transient_llm_error(exc) or attempt >= max_retries:
                break
            delay = backoff * (2**attempt)
            logger.info(
                "Generator %s transient error (attempt %s/%s), retry in %.1fs: %s",
                backend_label,
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            time.sleep(delay)

    assert last_exc is not None
    return _error_result(last_exc, backend_label)


def generate_reply(
    *,
    intent: str,
    system_prompt: str,
    user_prompt: str,
    gemini: GeminiGeneratorClient,
    local: LocalGeneratorClient,
) -> tuple[str, str, bool]:
    """
    Sinh text + tên backend đã dùng (local | gemini) + cờ is_error.
    Local lỗi → fallback Gemini (trừ khi GENERATOR_BACKEND=local và Gemini không có).
    Lỗi Gemini/Ollama được chuẩn hóa — không để exception nổi lên nguyên văn.
    """
    backend = resolve_backend_for_intent(intent)

    if backend == "local" and local.available:
        text, _, is_error = _call_with_retry(
            lambda: local.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                intent=intent,
            ),
            backend_label="local",
        )
        if not is_error:
            return text, "local", False
        if not gemini.available:
            return text, "local_error", True
        text, _, is_error = _call_with_retry(
            lambda: gemini.generate(system_prompt=system_prompt, user_prompt=user_prompt),
            backend_label="gemini_fallback",
        )
        if not is_error:
            return text, "gemini_fallback", False
        return text, "gemini_fallback_error", True

    if not gemini.available:
        return (
            normalize_llm_error_message(RuntimeError("No LLM available")),
            "none",
            True,
        )

    return _call_with_retry(
        lambda: gemini.generate(system_prompt=system_prompt, user_prompt=user_prompt),
        backend_label="gemini",
    )


def generator_status(
    *,
    gemini: GeminiGeneratorClient | None = None,
    local: LocalGeneratorClient | None = None,
) -> dict:
    g = gemini or GeminiGeneratorClient()
    loc = local or LocalGeneratorClient()
    gw = ChatCompletionGateway()
    mode = (settings.generator_backend or "auto").lower()
    llm_primary = (
        "chatbot_local"
        if gw.prefer_local and gw.local_configured
        else ("gemini" if gw.gemini_available else "none")
    )
    return {
        "generator_backend_mode": mode,
        "use_local_generator": settings.use_local_generator,
        "resolved_default": resolve_backend_for_intent("pathfinding"),
        "chatbot_llm_mode": settings.chatbot_llm_mode,
        "llm_primary": llm_primary,
        "chatbot_local_configured": gw.local_configured,
        "chatbot_local_base_url": settings.chatbot_local_base_url or None,
        "chatbot_local_model": settings.chatbot_local_model,
        "gemini_available": gw.gemini_available,
        "ollama_available": loc.available,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model_pathfinding": settings.ollama_model_pathfinding,
        "ollama_model_course_rec": settings.ollama_model_course_rec,
        "router": llm_primary,
        "advisory_form": llm_primary,
    }
