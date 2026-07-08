from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.enums import TargetRole, UserBackground, WeeklyTime, WEEKLY_TIME_FROM_FORM
from app.services.advisory_service import AdvisoryService

router = APIRouter(prefix="/api/advisory", tags=["advisory"])

_advisory_svc: AdvisoryService | None = None


def get_advisory_service() -> AdvisoryService:
    global _advisory_svc
    if _advisory_svc is None:
        _advisory_svc = AdvisoryService()
    return _advisory_svc


class AdvisoryStartRequest(BaseModel):
    background: str = Field(..., description="user_background enum value")
    role: str = Field(..., description="target_role enum value")
    # Cho phép rỗng khi user chọn "Chưa biết gì".
    known_skills: list[str] = Field(default_factory=list)
    goals: list[str] = Field(..., min_length=1)
    role_note: str | None = None
    weekly_time: str | None = Field(
        None,
        description="Enum lt5|5to10|10to20|gt20 hoặc nhãn tiếng Việt từ form",
    )
    initial_question: str | None = None
    target_role_text: str | None = None
    skill_profile: dict[str, list[str]] | None = None
    profile_id: str | None = Field(
        None, description="Tái sử dụng profile có sẵn (tạo session mới)"
    )
    session_id: str | None = None

    @field_validator("known_skills")
    @classmethod
    def strip_known_skills(cls, v: list[str]) -> list[str]:
        # known_skills được phép rỗng.
        return [s.strip() for s in v if s and str(s).strip()]

    @field_validator("goals")
    @classmethod
    def strip_goals(cls, v: list[str]) -> list[str]:
        out = [s.strip() for s in v if s and str(s).strip()]
        if not out:
            raise ValueError("Danh sách không được rỗng")
        return out


def _parse_background(value: str) -> UserBackground:
    try:
        return UserBackground(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "background",
                "message": f"Giá trị không hợp lệ: {value!r}. "
                f"Cho phép: {[e.value for e in UserBackground]}",
            },
        ) from exc


def _parse_role(value: str) -> TargetRole:
    try:
        return TargetRole(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "role",
                "message": f"Giá trị không hợp lệ: {value!r}. "
                f"Cho phép: {[e.value for e in TargetRole]}",
            },
        ) from exc


def _parse_weekly_time(value: str | None) -> WeeklyTime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    if raw in WEEKLY_TIME_FROM_FORM:
        return WEEKLY_TIME_FROM_FORM[raw]
    try:
        return WeeklyTime(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "weekly_time",
                "message": f"Giá trị không hợp lệ: {raw!r}. "
                f"Cho phép: {[e.value for e in WeeklyTime]} hoặc nhãn form tiếng Việt.",
            },
        ) from exc


@router.post("/start")
async def start_advisory(body: AdvisoryStartRequest):
    """Submit Form Khởi tạo Tư vấn: profile + session + advice_results."""
    try:
        target_role_text = (body.target_role_text or "").strip() or None
        skill_profile = body.skill_profile or {}

        if body.role == TargetRole.other.value and not target_role_text:
            raise HTTPException(
                status_code=422,
                detail={
                    "field": "target_role_text",
                    "message": "Bạn đã chọn 'Chưa rõ / khác'. Hãy nhập vị trí bạn muốn hướng tới.",
                },
            )

        known_skills = list(body.known_skills or [])
        for _, vals in skill_profile.items():
            for v in vals or []:
                sv = str(v).strip()
                if sv and sv.lower() not in {x.lower() for x in known_skills}:
                    known_skills.append(sv)

        if body.role == TargetRole.other.value and target_role_text:
            match = get_advisory_service().search_careers(target_role_text, limit=5)
            if not match.get("exact"):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "field": "target_role_text",
                        "message": "Vị trí chưa có trong dữ liệu Neo4j. Hãy nhập lại hoặc chọn gợi ý gần đúng.",
                        "suggestions": match.get("suggestions", []),
                    },
                )

        role_note_parts = [body.role_note or ""]
        if target_role_text:
            role_note_parts.append(f"Vị trí mong muốn: {target_role_text}")
        for k, vals in skill_profile.items():
            cleaned = [str(v).strip() for v in (vals or []) if str(v).strip()]
            if cleaned:
                role_note_parts.append(f"{k}: {', '.join(cleaned)}")
        role_note = "\n".join([x.strip() for x in role_note_parts if x and x.strip()]) or None

        return await get_advisory_service().submit_advisory_form(
            background=_parse_background(body.background),
            role=_parse_role(body.role),
            known_skills=known_skills,
            goals=body.goals,
            role_note=role_note,
            weekly_time=_parse_weekly_time(body.weekly_time),
            initial_question=body.initial_question,
            existing_profile_id=body.profile_id,
            career_label_override=target_role_text,
            existing_session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/session/{session_id}/advice")
async def get_session_advice(session_id: str):
    """Lấy kết quả tư vấn đã lưu (tránh gọi AI lại khi F5)."""
    advice = await get_advisory_service().get_cached_advice(session_id)
    if advice is None:
        return {"session_id": session_id, "advice": None}
    return {"session_id": session_id, "advice": advice}


@router.get("/roles/search")
async def search_roles(q: str, limit: int = 6):
    """Gợi ý role từ Neo4j theo query người dùng."""
    query = (q or "").strip()
    if not query:
        return {"query": "", "exact": False, "suggestions": []}
    result = get_advisory_service().search_careers(query, limit=limit)
    return {"query": query, "exact": bool(result.get("exact")), "suggestions": result.get("suggestions", [])}
