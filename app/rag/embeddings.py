from __future__ import annotations

import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Embed text via Gemini or OpenAI."""

    def __init__(self) -> None:
        self._provider = (settings.embedding_provider or "gemini").lower()
        self._gemini = None
        self._openai = None

        if self._provider == "openai" and settings.openai_api_key:
            from openai import OpenAI

            self._openai = OpenAI(api_key=settings.openai_api_key)
        elif settings.embedding_api_key:
            from google import genai

            self._gemini = genai.Client(api_key=settings.embedding_api_key)

    @property
    def available(self) -> bool:
        return self._gemini is not None or self._openai is not None

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._openai is not None:
            return self._embed_openai(texts)
        if self._gemini is not None:
            return self._embed_gemini(texts)
        raise RuntimeError("No embedding provider configured (GEMINI_API_KEY or OPENAI_API_KEY)")

    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        model = settings.embedding_model or "text-embedding-3-small"
        resp = self._openai.embeddings.create(input=texts, model=model)
        return [list(d.embedding) for d in resp.data]

    def _embed_gemini(self, texts: List[str]) -> List[List[float]]:
        from google.genai import types

        model = settings.embedding_model or "gemini-embedding-001"
        out: List[List[float]] = []
        for text in texts:
            try:
                result = self._gemini.models.embed_content(
                    model=model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        output_dimensionality=settings.embedding_dimensions,
                    ),
                )
                values = result.embeddings[0].values if result.embeddings else []
                out.append(list(values))
            except Exception as exc:
                logger.warning("Gemini embed failed: %s", exc)
                out.append([0.0] * settings.embedding_dimensions)
        return out
