"""
D-03 — LLM-as-a-Judge chấm chất lượng câu trả lời end-to-end.
Hỗ trợ Gemini | OpenAI | Groq | local OpenAI-compatible (CHATBOT_LOCAL_*).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import settings

_JUDGE_FALLBACKS = (
    "gemini-2.0-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-1.5-flash",
)

# Giới hạn output ngắn — tiết kiệm token free tier.
_JUDGE_MAX_OUTPUT_TOKENS = 256

JUDGE_SYSTEM_PROMPT = """Bạn là trọng tài (Judge) đánh giá chatbot tư vấn hướng nghiệp IT Graph-RAG.

Nhiệm vụ: chấm câu trả lời của chatbot so với Ground Truth kỳ vọng.

Quy tắc chấm:
1. faithfulness [0.0-1.0]: Mức độ câu trả lời bám sát dữ liệu đồ thị/ngữ cảnh được cung cấp,
   không tự bịa thêm nghề/kỹ năng/khóa học không có trong ground truth hoặc graph context.
   1.0 = hoàn toàn trung thực; 0.0 = phần lớn là bịa đặt.
2. skill_completeness [0.0-1.0]: Mức độ bao phủ các kỹ năng/lộ trình kỳ vọng trong expected_skills
   (không cần liệt kê 100% nhưng phải nhắc các mục cốt lõi). 1.0 = bao phủ tốt.
3. no_hallucination [boolean]: true nếu KHÔNG phát hiện thông tin khóa học/kỹ năng/nghề
   rõ ràng ngoài ground truth và graph context; false nếu có bịa đặt.

Chỉ trả về JSON hợp lệ, không markdown, không giải thích thêm:
{"faithfulness": <float>, "skill_completeness": <float>, "no_hallucination": <bool>}
"""


@dataclass
class JudgeScores:
    faithfulness: float
    skill_completeness: float
    no_hallucination: bool
    raw: dict[str, Any] | None = None
    backend_used: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "faithfulness": round(self.faithfulness, 4),
            "skill_completeness": round(self.skill_completeness, 4),
            "no_hallucination": self.no_hallucination,
        }
        if self.backend_used:
            out["backend_used"] = self.backend_used
        return out


class JudgeClient(Protocol):
    @property
    def available(self) -> bool: ...

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores: ...


def create_judge_client() -> JudgeClient:
    """Factory — chọn backend theo JUDGE_PROVIDER (gemini | openai | groq | local)."""
    provider = (settings.judge_provider or "gemini").lower()
    if provider == "local":
        return FallbackJudgeClient(
            [
                ("local", LocalJudgeClient()),
                ("groq", GroqJudgeClient()),
                ("gemini", GeminiJudgeClient()),
            ]
        )
    if provider == "openai":
        return OpenAIJudgeClient()
    if provider == "groq":
        return GroqJudgeClient()
    return GeminiJudgeClient()


class FallbackJudgeClient:
    """Try judges in order; attach backend_used to scores."""

    def __init__(self, chain: list[tuple[str, JudgeClient]]) -> None:
        self._chain = chain

    @property
    def available(self) -> bool:
        return any(c.available for _, c in self._chain)

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores:
        errors: list[str] = []
        for label, client in self._chain:
            if not client.available:
                continue
            try:
                result = client.score(
                    question=question,
                    answer=answer,
                    ground_truth=ground_truth,
                    graph_context=graph_context,
                )
                result.backend_used = label
                return result
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        raise RuntimeError(
            "Tất cả judge backends thất bại: " + "; ".join(errors[:3])
        )


def judge_model_label() -> str:
    """Nhãn model hiển thị trong báo cáo eval."""
    provider = (settings.judge_provider or "gemini").lower()
    if provider == "openai":
        return f"openai/{settings.judge_openai_model}"
    if provider == "groq":
        return f"groq/{settings.judge_groq_model}"
    if provider == "local":
        return f"local/{settings.judge_local_model}"
    return settings.judge_gemini_model


class GeminiJudgeClient:
    """Gemini judge — dùng key/model riêng, tiết kiệm token."""

    def __init__(self) -> None:
        self._client: genai.Client | None = None
        key = settings.judge_gemini_api_key
        if key:
            self._client = genai.Client(api_key=key)

    @property
    def available(self) -> bool:
        return self._client is not None

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores:
        if not self._client:
            raise RuntimeError(
                "Chưa cấu hình JUDGE_GEMINI_API_KEY hoặc GEMINI_API_KEY trong .env"
            )

        user_message = _build_user_message(
            question=question,
            answer=answer,
            ground_truth=ground_truth,
            graph_context=graph_context,
        )

        models = _judge_models_to_try()
        last_error: Exception | None = None

        for model in models:
            for attempt in range(2):
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=user_message,
                        config=types.GenerateContentConfig(
                            system_instruction=JUDGE_SYSTEM_PROMPT,
                            temperature=0.0,
                            max_output_tokens=_JUDGE_MAX_OUTPUT_TOKENS,
                            response_mime_type="application/json",
                        ),
                    )
                    text = (getattr(response, "text", None) or "").strip()
                    if text:
                        return _parse_judge_json(text)
                except genai_errors.ClientError as exc:
                    last_error = exc
                    if _is_quota_error(exc) and attempt == 0:
                        time.sleep(3)
                        continue
                    if _is_quota_error(exc) or _is_not_found_error(exc):
                        break
                    raise

        if last_error:
            raise RuntimeError(f"Lỗi Gemini Judge: {last_error}")
        raise RuntimeError("Không nhận được phản hồi từ Gemini Judge.")


class OpenAIJudgeClient:
    """OpenAI judge — gpt-4o-mini, JSON mode, tối ưu free tier."""

    def __init__(self) -> None:
        self._client = None
        key = settings.judge_openai_api_key
        if key:
            from openai import OpenAI

            self._client = OpenAI(api_key=key)

    @property
    def available(self) -> bool:
        return self._client is not None

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores:
        if not self._client:
            raise RuntimeError(
                "Chưa cấu hình JUDGE_OPENAI_API_KEY hoặc OPENAI_API_KEY trong .env"
            )
        model = (settings.judge_openai_model or "gpt-4o-mini").strip()
        return _score_with_chat_api(
            self._client,
            model=model,
            provider_name="OpenAI",
            question=question,
            answer=answer,
            ground_truth=ground_truth,
            graph_context=graph_context,
            check_insufficient_quota=True,
        )


class LocalJudgeClient:
    """Local judge — OpenAI-compatible proxy (CHATBOT_LOCAL_BASE_URL)."""

    def __init__(self) -> None:
        self._client = None
        base = (settings.chatbot_local_base_url or "").strip()
        if base:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.chatbot_local_api_key or "sk-chatbot-local",
                base_url=base.rstrip("/"),
                timeout=settings.chatbot_local_timeout_seconds,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores:
        if not self._client:
            raise RuntimeError(
                "Chưa cấu hình CHATBOT_LOCAL_BASE_URL trong .env (JUDGE_PROVIDER=local)"
            )
        model = (settings.judge_local_model or settings.chatbot_local_model).strip()
        return _score_with_chat_api(
            self._client,
            model=model,
            provider_name="Local",
            question=question,
            answer=answer,
            ground_truth=ground_truth,
            graph_context=graph_context,
            check_insufficient_quota=False,
        )


class GroqJudgeClient:
    """Groq judge — OpenAI-compatible API, free tier llama-3.1-8b-instant."""

    def __init__(self) -> None:
        self._client = None
        key = settings.judge_groq_api_key
        if key:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=key,
                base_url=settings.judge_groq_base_url,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def score(
        self,
        *,
        question: str,
        answer: str,
        ground_truth: dict[str, Any],
        graph_context: dict[str, Any] | None = None,
    ) -> JudgeScores:
        if not self._client:
            raise RuntimeError(
                "Chưa cấu hình JUDGE_GROQ_API_KEY hoặc GROQ_API_KEY trong .env"
            )
        model = (settings.judge_groq_model or "llama-3.1-8b-instant").strip()
        return _score_with_chat_api(
            self._client,
            model=model,
            provider_name="Groq",
            question=question,
            answer=answer,
            ground_truth=ground_truth,
            graph_context=graph_context,
            check_insufficient_quota=False,
        )


def _score_with_chat_api(
    client: Any,
    *,
    model: str,
    provider_name: str,
    question: str,
    answer: str,
    ground_truth: dict[str, Any],
    graph_context: dict[str, Any] | None,
    check_insufficient_quota: bool,
) -> JudgeScores:
    user_message = _build_user_message(
        question=question,
        answer=answer,
        ground_truth=ground_truth,
        graph_context=graph_context,
    )
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    last_error: Exception | None = None

    for attempt in range(2):
        for use_json_mode in (True, False):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "temperature": 0.0,
                    "max_tokens": _JUDGE_MAX_OUTPUT_TOKENS,
                    "messages": messages,
                }
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return _parse_judge_json(text)
            except Exception as exc:
                last_error = exc
                if check_insufficient_quota and _is_openai_insufficient_quota(exc):
                    raise RuntimeError(
                        "OpenAI Judge hết quota (insufficient_quota). "
                        "Kiểm tra https://platform.openai.com/usage"
                    ) from exc
                if use_json_mode:
                    continue
                if _is_openai_rate_limit(exc) and attempt == 0:
                    time.sleep(5)
                    break
                raise

    if last_error:
        raise RuntimeError(f"Lỗi {provider_name} Judge: {last_error}")
    raise RuntimeError(f"Không nhận được phản hồi từ {provider_name} Judge.")


def _build_user_message(
    *,
    question: str,
    answer: str,
    ground_truth: dict[str, Any],
    graph_context: dict[str, Any] | None,
    max_answer_chars: int = 2000,
) -> str:
    trimmed_answer = (answer or "")[:max_answer_chars]
    gt = dict(ground_truth)
    eval_intent = str(gt.get("eval_intent") or gt.get("intent") or "")
    if eval_intent == "skills_gap":
        trimmed_answer = (answer or "")[: min(max_answer_chars, 1500)]
    for key in ("expected_skills", "expected_courses"):
        val = gt.get(key)
        if isinstance(val, list) and len(val) > 20:
            gt[key] = val[:20]
    ctx = graph_context or {}
    if isinstance(ctx, dict):
        ctx = dict(ctx)
        for key in ("competencies", "courses", "skills_missing", "skills_known"):
            val = ctx.get(key)
            if isinstance(val, list) and len(val) > 15:
                ctx[key] = val[:15]
    payload = {
        "question": question,
        "chatbot_answer": trimmed_answer,
        "ground_truth": gt,
        "graph_context": ctx,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _judge_models_to_try() -> list[str]:
    primary = (settings.judge_gemini_model or "").strip()
    order: list[str] = []
    seen: set[str] = set()
    for name in [primary, *_JUDGE_FALLBACKS]:
        if name and name not in seen:
            seen.add(name)
            order.append(name)
    return order


def _parse_judge_json(text: str) -> JudgeScores:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Judge JSON không hợp lệ: {text[:200]}")
        data = json.loads(match.group(0))

    faith = float(data.get("faithfulness", 0.0))
    complete = float(data.get("skill_completeness", 0.0))
    no_hall = bool(data.get("no_hallucination", False))
    faith = max(0.0, min(1.0, faith))
    complete = max(0.0, min(1.0, complete))
    return JudgeScores(
        faithfulness=faith,
        skill_completeness=complete,
        no_hallucination=no_hall,
        raw=data if isinstance(data, dict) else None,
    )


def _is_quota_error(exc: genai_errors.ClientError) -> bool:
    detail = str(exc)
    return "429" in detail or "RESOURCE_EXHAUSTED" in detail or "quota" in detail.lower()


def _is_not_found_error(exc: genai_errors.ClientError) -> bool:
    detail = str(exc).lower()
    return "404" in detail or "not found" in detail


def _is_openai_rate_limit(exc: Exception) -> bool:
    detail = str(exc).lower()
    if "insufficient_quota" in detail:
        return False
    return "429" in detail or "rate limit" in detail or "rate_limit" in detail


def _is_openai_insufficient_quota(exc: Exception) -> bool:
    return "insufficient_quota" in str(exc).lower()
