"""CHATBOT_LLM_MODE=1: local Gemini 3.5 trước; =2: chỉ Gemini 2.5."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, List

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core import config

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_FALLBACKS = (
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
)


class ChatCompletionGateway:
    def __init__(self) -> None:
        self._gemini: genai.Client | None = None
        if config.settings.gemini_api_key:
            self._gemini = genai.Client(api_key=config.settings.gemini_api_key)
        self._openai = None
        if config.settings.chatbot_llm_mode == 1 and config.settings.chatbot_local_base_url:
            from openai import OpenAI

            self._openai = OpenAI(
                base_url=config.settings.chatbot_local_base_url.rstrip("/"),
                api_key=config.settings.chatbot_local_api_key or "sk-chatbot-local",
                timeout=config.settings.chatbot_local_timeout_seconds,
            )

    @property
    def prefer_local(self) -> bool:
        return config.settings.chatbot_llm_mode == 1

    @property
    def local_configured(self) -> bool:
        return self._openai is not None

    @property
    def gemini_available(self) -> bool:
        return self._gemini is not None

    @property
    def available(self) -> bool:
        return self.local_configured or self.gemini_available

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        primary_model: str,
        fallback_models: str,
    ) -> tuple[str, str]:
        if self.prefer_local and self.local_configured:
            try:
                text = self._local_complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_output_tokens,
                    json_mode=False,
                )
                if text:
                    return text, "chatbot_local"
            except Exception as exc:
                logger.warning(
                    "Local chatbot API failed (%s), fallback Gemini 2.5",
                    exc,
                )
        elif self.prefer_local and not self.local_configured:
            logger.warning(
                "CHATBOT_LLM_MODE=1 nhưng thiếu CHATBOT_LOCAL_BASE_URL — dùng Gemini 2.5"
            )

        text = self._gemini_generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            primary_model=primary_model,
            fallback_models=fallback_models,
        )
        return text, "gemini"

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        primary_model: str,
        fallback_models: str,
        response_schema: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        if self.prefer_local and self.local_configured:
            try:
                text = self._local_complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_output_tokens,
                    json_mode=True,
                )
                if text:
                    return text, "chatbot_local"
            except Exception as exc:
                logger.warning(
                    "Local chatbot API JSON failed (%s), fallback Gemini 2.5",
                    exc,
                )
        elif self.prefer_local and not self.local_configured:
            logger.warning(
                "CHATBOT_LLM_MODE=1 nhưng thiếu CHATBOT_LOCAL_BASE_URL — dùng Gemini 2.5"
            )

        text = self._gemini_generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            primary_model=primary_model,
            fallback_models=fallback_models,
            response_schema=response_schema,
        )
        return text, "gemini"

    def _local_complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        if not self._openai:
            raise RuntimeError("Local chatbot API not configured")
        kwargs: dict[str, Any] = {
            "model": config.settings.chatbot_local_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._openai.chat.completions.create(**kwargs)
        choice = response.choices[0].message
        text = (choice.content or "").strip()
        if not text:
            raise RuntimeError("Local chatbot API returned empty content")
        if json_mode:
            json.loads(text)
        return text

    def _gemini_generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        primary_model: str,
        fallback_models: str,
    ) -> str:
        if not self._gemini:
            raise RuntimeError(
                "Chưa cấu hình GEMINI_API_KEY và local chatbot API không khả dụng."
            )
        models = _models_to_try(primary_model, fallback_models)
        last_error: genai_errors.ClientError | None = None
        for model in models:
            for attempt in range(2):
                try:
                    response = self._gemini.models.generate_content(
                        model=model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=max_output_tokens,
                        ),
                    )
                    text = (getattr(response, "text", None) or "").strip()
                    if text:
                        return text
                except genai_errors.ClientError as exc:
                    last_error = exc
                    if _is_quota_error(exc) and attempt == 0:
                        time.sleep(2)
                        continue
                    if _is_quota_error(exc) or _is_not_found_error(exc):
                        break
                    raise
        if last_error:
            raise RuntimeError(f"Lỗi Gemini: {last_error}")
        raise RuntimeError("Không nhận được phản hồi từ Gemini.")

    def _gemini_generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        primary_model: str,
        fallback_models: str,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        if not self._gemini:
            raise RuntimeError(
                "Chưa cấu hình GEMINI_API_KEY và local chatbot API không khả dụng."
            )
        models = _models_to_try(primary_model, fallback_models)
        last_error: genai_errors.ClientError | None = None
        for model in models:
            for attempt in range(2):
                try:
                    config_kwargs: dict[str, Any] = {
                        "system_instruction": system_prompt,
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                        "response_mime_type": "application/json",
                    }
                    if response_schema is not None:
                        config_kwargs["response_schema"] = response_schema
                    response = self._gemini.models.generate_content(
                        model=model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )
                    text = (getattr(response, "text", None) or "").strip()
                    if text:
                        return text
                except genai_errors.ClientError as exc:
                    last_error = exc
                    if _is_quota_error(exc) and attempt == 0:
                        time.sleep(2)
                        continue
                    if _is_quota_error(exc) or _is_not_found_error(exc):
                        break
                    raise
        if last_error:
            raise RuntimeError(f"Lỗi Gemini JSON: {last_error}")
        raise RuntimeError("Không nhận được phản hồi JSON từ Gemini.")


def _models_to_try(primary: str, fallback_csv: str) -> List[str]:
    extra = [m.strip() for m in fallback_csv.split(",") if m.strip()]
    order: List[str] = []
    seen: set[str] = set()
    for name in [primary, *extra, *_DEFAULT_GEMINI_FALLBACKS]:
        if name and name not in seen:
            seen.add(name)
            order.append(name)
    return order


def _is_quota_error(exc: genai_errors.ClientError) -> bool:
    detail = str(exc)
    return "429" in detail or "RESOURCE_EXHAUSTED" in detail or "quota" in detail.lower()


def _is_not_found_error(exc: genai_errors.ClientError) -> bool:
    detail = str(exc).lower()
    return "404" in detail or "not found" in detail
