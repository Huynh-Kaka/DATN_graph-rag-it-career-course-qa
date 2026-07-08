from __future__ import annotations

import enum


class UserBackground(str, enum.Enum):
    student = "student"
    grad = "grad"
    fresher = "fresher"
    career_switch = "career_switch"
    self_taught = "self_taught"


class TargetRole(str, enum.Enum):
    backend = "backend"
    frontend = "frontend"
    fullstack = "fullstack"
    data = "data"
    devops = "devops"
    mobile = "mobile"
    pm = "pm"
    other = "other"


class WeeklyTime(str, enum.Enum):
    lt5 = "lt5"
    h5to10 = "5to10"
    h10to20 = "10to20"
    gt20 = "gt20"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


ROLE_DISPLAY: dict[str, str] = {
    TargetRole.backend.value: "Backend Developer",
    TargetRole.frontend.value: "Frontend Developer",
    TargetRole.fullstack.value: "Fullstack Developer",
    TargetRole.data.value: "Data Analyst / Data Scientist",
    TargetRole.devops.value: "DevOps / Cloud Engineer",
    TargetRole.mobile.value: "Mobile Developer",
    TargetRole.pm.value: "IT Project Manager / BA",
    TargetRole.other.value: "Chưa rõ / khác",
}

BACKGROUND_DISPLAY: dict[str, str] = {
    UserBackground.student.value: "Sinh viên năm 1–3",
    UserBackground.grad.value: "Sinh viên năm 4 / sắp ra trường",
    UserBackground.fresher.value: "Fresher (0–1 năm)",
    UserBackground.career_switch.value: "Đang đi làm, chuyển sang IT",
    UserBackground.self_taught.value: "Tự học IT ngoài giờ",
}

WEEKLY_TIME_DISPLAY: dict[str, str] = {
    WeeklyTime.lt5.value: "< 5 giờ/tuần",
    WeeklyTime.h5to10.value: "5–10 giờ/tuần",
    WeeklyTime.h10to20.value: "10–20 giờ/tuần",
    WeeklyTime.gt20.value: "> 20 giờ/tuần",
}

# Form UI labels → DB enum (weekly_time)
WEEKLY_TIME_FROM_FORM: dict[str, WeeklyTime] = {
    "< 5 giờ/tuần": WeeklyTime.lt5,
    "5–10 giờ/tuần": WeeklyTime.h5to10,
    "10–20 giờ/tuần": WeeklyTime.h10to20,
    "> 20 giờ/tuần": WeeklyTime.gt20,
}
