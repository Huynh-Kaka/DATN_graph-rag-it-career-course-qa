from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str
    intent: str | None = None
