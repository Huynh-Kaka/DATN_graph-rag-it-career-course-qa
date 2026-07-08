"""
Kiểm tra vị trí LLM: Gemini router/generator, Ollama, embedding.

Chạy: python scripts/check_llm_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.core.config import settings
from app.services.generator_backend import generator_status
from app.services.gemini_generator_client import GeminiGeneratorClient
from app.services.local_generator_client import LocalGeneratorClient
from app.rag.embeddings import EmbeddingClient


def main() -> None:
    print("=== LLM placement check ===\n")
    print(f"GENERATOR_BACKEND={settings.generator_backend}")
    print(f"USE_LOCAL_GENERATOR={settings.use_local_generator}")
    print(f"GEMINI_MODEL={settings.gemini_model}")
    print(f"ROUTER_MODEL={settings.router_model}")
    print()

    gen = GeminiGeneratorClient()
    local = LocalGeneratorClient()
    emb = EmbeddingClient()

    router_ok = bool(settings.gemini_api_key)
    print(f"Router (Gemini):     {'OK' if router_ok else 'MISSING KEY'}")
    print(f"Generator (Gemini):  {'OK' if gen.available else 'MISSING KEY'}")
    print(f"Generator (Ollama):  {'OK' if local.available else 'not running / no models'}")
    print(f"Embedding:           {'OK' if emb.available else 'MISSING KEY'}")
    print()
    print("Status dict:", generator_status())
    print()
    if settings.use_local_generator and not local.available:
        print("WARN: USE_LOCAL_GENERATOR=1 but Ollama unavailable → will fallback Gemini.")
    if not gen.available:
        print("ERROR: GEMINI_API_KEY required for router and fallback generator.")
        sys.exit(1)
    print("OK: minimum Gemini config present.")


if __name__ == "__main__":
    main()
