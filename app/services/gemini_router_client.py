from __future__ import annotations

import json

from app.core.config import settings
from app.services.chat_completion_gateway import ChatCompletionGateway


class GeminiRouterClient:
    """Intent Router — ưu tiên local OpenAI-compatible API, fallback Gemini JSON."""

    def __init__(self) -> None:
        self._gateway = ChatCompletionGateway()

    def classify(self, *, system_prompt: str, user_message: str) -> str:
        text, _backend = self._gateway.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_message,
            temperature=settings.router_temperature,
            max_output_tokens=512,
            primary_model=settings.router_model,
            fallback_models=settings.router_fallback_models,
        )
        json.loads(text)
        return text
