#!/usr/bin/env python3
"""
Kiểm thử toàn luồng (Bước 5) — chạy: python scripts/test_chat_scenarios.py
Cần Neo4j + GEMINI_API_KEY (generator); router cũng dùng Gemini.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.chat_service import ChatService  # noqa: E402

SCENARIOS = [
    ("out-of-domain", "Hôm nay nấu món gì ngon?"),
    ("pathfinding", "Làm Backend Developer cần học những gì?"),
    ("course-followup", "vậy khóa SQL nào phù hợp?"),
]


async def run_scenarios() -> int:
    chat = ChatService()
    session_id = None
    failed = 0

    print("=== Chat E2E scenarios ===\n")
    for name, message in SCENARIOS:
        print(f"--- {name}: {message!r} ---")
        result = await chat.handle_message(message=message, session_id=session_id)
        session_id = result["session_id"]
        route = result.get("route") or {}
        print(f"  intent: {route.get('intent')}  domain: {route.get('domain')}")
        print(f"  career: {result.get('session', {}).get('career')}")
        reply_preview = (result.get("reply") or "")[:200]
        print(f"  reply: {reply_preview}...\n")

        if name == "out-of-domain" and "IT" not in (result.get("reply") or ""):
            print("  FAIL: expected out-of-domain reply")
            failed += 1
        if name == "pathfinding" and route.get("intent") != "pathfinding":
            print("  FAIL: expected pathfinding")
            failed += 1
        if name == "course-followup" and route.get("intent") != "course_rec":
            print("  FAIL: expected course_rec follow-up")
            failed += 1

    print(f"Done. Failed: {failed}")
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(run_scenarios())


if __name__ == "__main__":
    raise SystemExit(main())
