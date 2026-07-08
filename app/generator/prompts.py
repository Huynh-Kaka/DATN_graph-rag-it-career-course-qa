from __future__ import annotations

import json
from typing import Any

from app.db.enums import BACKGROUND_DISPLAY, WEEKLY_TIME_DISPLAY
from app.intent.models import IntentRouteResult
from app.session.context import build_history_block
from app.session.store import SessionState

_GROUNDING = (
    "QUY TẮC BẮT BUỘC:\n"
    "- CHỈ dùng dữ liệu được cung cấp trong phần DỮ LIỆU NEO4J / HỒ SƠ. Không bịa thêm khóa học, kỹ năng, hoặc tổ chức.\n"
    "- Nếu dữ liệu trống hoặc báo lỗi, nói rõ và hướng dẫn user hỏi lại hoặc đổi từ khóa.\n"
    "- Trả lời tiếng Việt, thân thiện, gọn (dưới 500 từ trừ khi liệt kê khóa học).\n"
)

SLOT_FILL_SYSTEM = f"""Bạn là AI tư vấn hướng nghiệp IT.
Nhiệm vụ: hỏi ngược user để thu thập thông tin còn thiếu. KHÔNG gọi Neo4j, KHÔNG bịa dữ liệu nghề/khóa học cụ thể.

{_GROUNDING}

Khi thiếu career: hỏi nghề IT mục tiêu (ví dụ Data Analyst, Backend Developer).
Khi thiếu competency: hỏi kỹ năng/công nghệ muốn học (ví dụ Python, SQL).
Có thể gợi ý 2–3 ví dụ ngắn. Kết thúc bằng một câu hỏi mở."""

PATHFINDING_SYSTEM = f"""Bạn là AI tư vấn hướng nghiệp IT.
Nhiệm vụ: tổng hợp dữ liệu Neo4j về kỹ năng cần cho một nghề thành câu trả lời tự nhiên, có cấu trúc.

{_GROUNDING}

Cấu trúc gợi ý:
1) Tóm tắt ngắn nghề và phạm vi
2) Nếu có skills_known / skills_missing trong dữ liệu: nêu rõ «Đã có» và «Cần học» (KHÔNG liệt kê skill đã có vào phần cần học)
3) Chỉ nhóm skills_missing theo loại (ngôn ngữ, framework, tool…)
4) Gợi ý ưu tiên học trước (nếu có priority)
5) KHÔNG dùng markdown (**bold**). Chỉ văn bản thuần.
6) Kết thúc bằng MỘT câu hỏi dẫn dắt."""

COURSE_REC_SYSTEM = f"""Bạn là AI tư vấn hướng nghiệp IT.
Nhiệm vụ: trình bày danh sách khóa học từ Neo4j cho một kỹ năng cụ thể.

{_GROUNDING}
- Nếu found=false hoặc courses rỗng: chỉ nói không có dữ liệu cho kỹ năng/chứng chỉ user hỏi; KHÔNG đưa khóa học khác (vd. ngôn ngữ C khi user hỏi CBAP).

Cấu trúc gợi ý:
1) Một câu mở đầu về kỹ năng được tra cứu
2) Danh sách đánh số từng khóa: tên, tổ chức, cấp độ (level), phụ đề (subtitle), link nếu có
3) Gợi ý ngắn cách chọn khóa phù hợp (dựa trên level/subtitle có trong dữ liệu)
4) Kết thúc bằng MỘT câu hỏi dẫn dắt (vd. muốn so sánh thêm khóa khác không)."""

COMPETENCY_RELATION_SYSTEM = f"""Bạn là AI tư vấn hướng nghiệp IT.
Nhiệm vụ: giải thích tiên quyết, chứng chỉ, hoặc kỹ năng liên quan từ dữ liệu Neo4j.

{_GROUNDING}
- CHỈ dùng quan hệ có trong JSON (outgoing/incoming). KHÔNG bịa prerequisite.
- Nếu outgoing và incoming rỗng: nói chưa có dữ liệu liên quan.
- KHÔNG hiển thị tên quan hệ kỹ thuật (BUILT_ON, VALIDATES, outgoing, incoming).
- KHÔNG hiển thị mã nội bộ (L_PY, F_DJANGO, ...).
- KHÔNG dùng markdown (**bold**, ## tiêu đề). Chỉ văn bản thuần, gạch đầu dòng • nếu cần.
- Diễn đạt tự nhiên: "Django được xây dựng trên Python — bạn nên học Python trước."

Cấu trúc: một câu tóm tắt → liệt kê quan hệ bằng tiếng Việt → gợi ý bước học tiếp."""


def build_competency_relation_user_prompt(
    *,
    user_message: str,
    graph_data: dict[str, Any],
    state: SessionState,
) -> str:
    return (
        f"{build_history_block(state)}"
        f"## Câu hỏi người dùng\n{user_message}\n\n"
        f"## Dữ liệu Neo4j (competency relations)\n"
        f"{json.dumps(graph_data, ensure_ascii=False, indent=2)}\n\n"
        f"{_profile_block(state)}"
    )


def build_slot_fill_user_prompt(
    *,
    user_message: str,
    route: IntentRouteResult,
    state: SessionState,
) -> str:
    profile = _profile_block(state)
    history = build_history_block(state)
    return (
        f"{history}"
        f"## Câu hỏi người dùng\n{user_message}\n\n"
        f"## Intent / slot thiếu\n"
        f"- intent: {route.intent}\n"
        f"- missing_slots: {route.missing_slots}\n"
        f"- entities: {json.dumps(route.entities.model_dump(), ensure_ascii=False)}\n\n"
        f"{profile}"
    )


def build_pathfinding_user_prompt(
    *,
    user_message: str,
    graph_data: dict[str, Any],
    state: SessionState,
    competency_scope_label: str | None = None,
) -> str:
    scope_block = ""
    if competency_scope_label:
        scope_block = (
            f"## Phạm vi câu hỏi\n"
            f"Người dùng CHỈ hỏi về nhóm: {competency_scope_label}.\n"
            f"CHỈ trả lời về nhóm này; KHÔNG liệt kê ngôn ngữ, framework, tool, "
            f"kiến thức hay chứng chỉ nếu không thuộc nhóm trên.\n"
            f"Dữ liệu Neo4j bên dưới đã được lọc theo nhóm này.\n\n"
        )
    return (
        f"{build_history_block(state)}"
        f"## Câu hỏi người dùng\n{user_message}\n\n"
        f"{scope_block}"
        f"## Dữ liệu Neo4j (pathfinding)\n"
        f"{json.dumps(graph_data, ensure_ascii=False, indent=2)}\n\n"
        f"{_profile_block(state)}"
    )


def build_course_rec_user_prompt(
    *,
    user_message: str,
    graph_data: dict[str, Any],
    state: SessionState,
) -> str:
    return (
        f"{build_history_block(state)}"
        f"## Câu hỏi người dùng\n{user_message}\n\n"
        f"## Dữ liệu Neo4j (course recommendation)\n"
        f"{json.dumps(graph_data, ensure_ascii=False, indent=2)}\n\n"
        f"{_profile_block(state)}"
    )


def _profile_block(state: SessionState) -> str:
    if not state.profile:
        if state.career:
            return f"## Hồ sơ\n- Nghề đang thảo luận: {state.career}\n"
        return "## Hồ sơ\n(Chưa có — không suy diễn thêm.)\n"

    p = state.profile
    bg = BACKGROUND_DISPLAY.get(p.background, p.background)
    wt = WEEKLY_TIME_DISPLAY.get(p.weekly_time or "", p.weekly_time or "chưa rõ")
    lines = [
        "## Hồ sơ (đã điền form — KHÔNG hỏi lại các mục sau)",
        f"- user_background: {p.background} ({bg})",
        f"- target_role: {p.target_role_label}",
    ]
    if p.role_note:
        lines.append(f"- role_note: {p.role_note}")
    if p.known_skills:
        lines.append(f"- known_skills: {', '.join(p.known_skills)}")
    lines.append(f"- weekly_time: {wt}")
    if p.goals:
        lines.append(f"- goals: {', '.join(p.goals)}")
    if p.initial_question:
        lines.append(f"- initial_question: {p.initial_question}")
    return "\n".join(lines) + "\n"
