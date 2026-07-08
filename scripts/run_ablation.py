"""
Run minimal ablation scenarios (B3 vs +vector vs +local).

Chạy: python scripts/run_ablation.py --message "Backend cần học gì?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)


async def run_once(label: str, service) -> dict:
    t0 = time.perf_counter()
    out = await service.handle_message(message=MSG, session_id=None)
    elapsed = time.perf_counter() - t0
    return {
        "label": label,
        "latency_s": round(elapsed, 3),
        "reply_len": len(out.get("reply") or ""),
        "intent": (out.get("route") or {}).get("intent"),
        "evidence": out.get("evidence"),
    }


MSG = ""


async def main_async(message: str) -> None:
    global MSG
    MSG = message

    from app.core.config import settings
    from app.generator.response_generator import ResponseGenerator
    from app.rag.retriever import VectorRetriever
    from app.services.chat_service import ChatService

    results = []

    # B3: full chat (default)
    svc = ChatService()
    results.append(await run_once("B3_full", svc))

    # B3 - vector: stub retriever
    class _NoVector(VectorRetriever):
        def retrieve_docs(self, query: str, top_k: int = 3):
            return []

    svc_no_vec = ChatService(retriever=_NoVector())
    results.append(await run_once("B3_no_vector", svc_no_vec))

    # B3 + local if enabled
    if settings.use_local_generator:
        results.append(await run_once("B4_local_generator", svc))

    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", type=str, required=True)
    args = parser.parse_args()
    asyncio.run(main_async(args.message))


if __name__ == "__main__":
    main()
