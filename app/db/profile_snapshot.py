from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.enums import ROLE_DISPLAY


@dataclass
class ProfileSnapshot:
    profile_id: str
    background: str
    role: str
    role_note: str | None
    known_skills: list[str]
    weekly_time: str | None
    goals: list[str]
    initial_question: str | None
    profile_completed: bool = True

    @property
    def target_role_label(self) -> str:
        return ROLE_DISPLAY.get(self.role, self.role)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "user_background": self.background,
            "target_role": self.role,
            "target_role_label": self.target_role_label,
            "role_note": self.role_note or "",
            "known_skills": self.known_skills,
            "weekly_time": self.weekly_time or "",
            "goals": self.goals,
            "initial_question": self.initial_question or "",
        }
