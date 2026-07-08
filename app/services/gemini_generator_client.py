from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.chat_completion_gateway import ChatCompletionGateway


class GeminiGeneratorClient:
    """Response Generator — ưu tiên local OpenAI-compatible API, fallback Gemini."""

    def __init__(self) -> None:
        self._gateway = ChatCompletionGateway()

    @property
    def available(self) -> bool:
        return self._gateway.available

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        text, _backend = self._gateway.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.generator_temperature,
            max_output_tokens=1024,
            primary_model=settings.generator_model,
            fallback_models=settings.generator_fallback_models,
        )
        return text

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int = 2048,
    ) -> str:
        text, _backend = self._gateway.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.generator_temperature,
            max_output_tokens=max_output_tokens,
            primary_model=settings.generator_model,
            fallback_models=settings.generator_fallback_models,
            response_schema=response_schema,
        )
        return text
