from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.profile_snapshot import ProfileSnapshot
from app.session.competency_types import COMPETENCY_TYPE_ORDER, Phase
from app.session.models import ChatTurn


@dataclass
class SessionState:
    session_id: str
    profile_id: str | None = None
    profile: ProfileSnapshot | None = None
    career: str | None = None
    competency: str | None = None
    competency_type_index: int = 0
    known_by_type: dict[str, list[str]] = field(default_factory=dict)
    phase: Phase = "idle"
    missing_slots: list[str] = field(default_factory=list)
    last_route: dict[str, Any] | None = None
    last_intent: str | None = None
    last_domain_out: bool = False
    pending_message: str = ""
    messages: list[ChatTurn] = field(default_factory=list)

    @property
    def profile_completed(self) -> bool:
        return self.profile is not None and self.profile.profile_completed

    @property
    def target_role(self) -> str:
        if self.profile:
            return self.profile.target_role_label
        return self.career or ""

    def merge_route(self, route: dict[str, Any]) -> None:
        self.last_route = route
        entities = route.get("entities") or {}
        if entities.get("career"):
            self.career = entities["career"]
        if entities.get("competency"):
            self.competency = entities["competency"]
        self.missing_slots = list(route.get("missing_slots") or [])

    def append_message(
        self, role: str, content: str, *, max_messages: int = 24, intent: str | None = None
    ) -> None:
        text = (content or "").strip()
        if not text:
            return
        self.messages.append(ChatTurn(role=role, content=text, intent=intent))
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    @property
    def current_competency_type(self) -> str | None:
        if self.competency_type_index < 0:
            return None
        if self.competency_type_index >= len(COMPETENCY_TYPE_ORDER):
            return None
        return COMPETENCY_TYPE_ORDER[self.competency_type_index]

    def reset_competency_flow(self) -> None:
        self.competency_type_index = 0
        self.known_by_type = {}
        self.phase = "collecting"

    def record_known_for_type(self, type_code: str, skills: list[str]) -> None:
        if not type_code or not skills:
            return
        bucket = self.known_by_type.setdefault(type_code, [])
        seen = {s.lower() for s in bucket}
        for skill in skills:
            label = (skill or "").strip()
            if not label:
                continue
            key = label.lower()
            if key not in seen:
                seen.add(key)
                bucket.append(label)

    def all_known_skills(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for type_code in COMPETENCY_TYPE_ORDER:
            for skill in self.known_by_type.get(type_code) or []:
                key = skill.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(skill)
        return out

    def to_public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "career": self.career,
            "competency": self.competency,
            "competency_type_index": self.competency_type_index,
            "current_competency_type": self.current_competency_type,
            "known_by_type": dict(self.known_by_type),
            "phase": self.phase,
            "last_intent": self.last_intent,
            "missing_slots": self.missing_slots,
            "profile_completed": self.profile_completed,
            "message_count": len(self.messages),
        }
        if self.profile:
            out["profile"] = self.profile.to_prompt_dict()
        return out
