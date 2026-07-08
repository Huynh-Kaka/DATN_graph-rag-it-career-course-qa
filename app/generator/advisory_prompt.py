from __future__ import annotations

import json
from typing import Any

from app.advice.schema import normalize_advice_payload
from app.db.enums import BACKGROUND_DISPLAY, ROLE_DISPLAY, WEEKLY_TIME_DISPLAY
from app.db.profile_snapshot import ProfileSnapshot


def build_advisory_system_prompt() -> str:
    return """Bạn là Chuyên gia Tư vấn IT (IT Career Advisor).

Nhiệm vụ: Đọc hồ sơ người dùng đã được cung cấp và trả về kết quả tư vấn có cấu trúc (JSON) theo schema.

QUY TẮC BẮT BUỘC:
1. Đọc đầy đủ ngữ cảnh: user_background, target_role, known_skills, weekly_time, goals, initial_question.
2. TUYỆT ĐỐI KHÔNG hỏi lại thông tin đã có trong hồ sơ (xuất phát điểm, nghề mục tiêu, kỹ năng đã biết, thời gian học, mục tiêu tư vấn).
3. Trực tiếp phân tích skills gap, đề xuất lộ trình THEO TỪNG THÁNG (month: 1, 2, 3, ... — ít nhất 4 tháng, tối đa ~12 tháng tùy mục tiêu).
4. Mỗi phần tử roadmap PHẢI có: month, topics (2-4 chủ đề), milestone (cột mốc cụ thể), courses (1-3 khóa học: title, platform).
   - url (nếu có) PHẢI là link trực tiếp tới TRANG KHÓA HỌC (vd. coursera.org/learn/...), KHÔNG dùng trang chủ nền tảng (coursera.org, udemy.com, w3schools.com).
   - Nếu không chắc link khóa cụ thể, bỏ trống url — hệ thống sẽ bổ sung từ graph.
5. recommended_courses: tổng hợp các khóa nổi bật (có thể trùng với courses trong roadmap).
6. Giải quyết initial_question nếu có; nếu không, tư vấn theo goals.
7. summary_vi: Tiếng Việt, thân thiện, thực tế, 2-4 đoạn — tóm tắt gap, lộ trình và khóa học như một câu trả lời hoàn chỉnh.
8. skills_gap.missing / weak: kỹ năng kỹ thuật (ngôn ngữ, framework, công cụ…). Kỹ năng mềm và chứng chỉ sẽ được hệ thống bổ sung từ graph — không cần liệt kê trong JSON.
9. Chỉ trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON."""


def build_advisory_user_prompt(profile: ProfileSnapshot, *, graph_context: list[str] | None = None) -> str:
    bg = BACKGROUND_DISPLAY.get(profile.background, profile.background)
    role = ROLE_DISPLAY.get(profile.role, profile.role)
    wt = WEEKLY_TIME_DISPLAY.get(profile.weekly_time or "", profile.weekly_time or "chưa rõ")
    skills = ", ".join(profile.known_skills) if profile.known_skills else "chưa rõ"
    goals = ", ".join(profile.goals) if profile.goals else "chưa rõ"

    lines = [
        "## Hồ sơ người dùng",
        f"- user_background: {profile.background} ({bg})",
        f"- target_role: {profile.role} ({role})",
    ]
    if profile.role_note:
        lines.append(f"- role_note: {profile.role_note}")
    lines.append(f"- known_skills: {skills}")
    lines.append(f"- weekly_time: {profile.weekly_time or 'chưa rõ'} ({wt})")
    lines.append(f"- goals: {goals}")
    if profile.initial_question:
        lines.append(f"- initial_question: {profile.initial_question}")

    if graph_context:
        lines.append("\n## Ngữ cảnh từ knowledge graph (Neo4j)")
        for item in graph_context[:8]:
            lines.append(f"- {item}")

    lines.append(
        "\nHãy trả về JSON với skills_gap, roadmap (mỗi tháng có topics, milestone, courses), "
        "recommended_courses, estimated_months, summary_vi."
    )
    return "\n".join(lines)


def format_advice_reply(structured: dict[str, Any]) -> str:
    """Chuyển JSON tư vấn thành tin nhắn hiển thị chat."""
    norm = normalize_advice_payload(structured)
    summary = (norm.get("summary_vi") or "").strip()
    if summary:
        return summary

    parts: list[str] = []
    gap = norm["skills_gap"]
    missing = gap.get("missing") or []
    weak = gap.get("weak") or []
    if missing or weak:
        parts.append("**Khoảng cách kỹ năng**")
        if missing:
            parts.append("- Cần bổ sung: " + ", ".join(missing[:12]))
        if weak:
            parts.append("- Nên củng cố: " + ", ".join(weak[:12]))
        soft = gap.get("soft_skills") or []
        certs = gap.get("certifications") or []
        if soft:
            parts.append("- Kỹ năng mềm: " + ", ".join(soft[:10]))
        if certs:
            parts.append("- Chứng chỉ tham khảo: " + ", ".join(certs[:10]))

    months = norm.get("estimated_months")
    if months is not None:
        parts.append(f"\n**Ước tính:** khoảng {months} tháng để sẵn sàng đi làm (tham khảo).")

    return "\n".join(parts) if parts else json.dumps(norm, ensure_ascii=False, indent=2)
