from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalGeneratorClient:
    """Ollama HTTP API — same interface surface as GeminiGeneratorClient.generate()."""

    def __init__(self) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self._timeout = settings.ollama_timeout_seconds

    @property
    def available(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"{self._base}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        intent: str = "pathfinding",
    ) -> str:
        model = (
            settings.ollama_model_course_rec
            if intent == "course_rec"
            else settings.ollama_model_pathfinding
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(f"{self._base}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise RuntimeError("Ollama returned empty content")
        return content
