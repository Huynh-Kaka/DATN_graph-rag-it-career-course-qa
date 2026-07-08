from __future__ import annotations

from app.intent.models import Intent

_INTENT_LABELS: dict[Intent, str] = {
    "pathfinding": "lộ trình nghề nghiệp và kỹ năng cần có",
    "course_rec": "gợi ý khóa học cụ thể",
    "subject_career": "liên kết môn học trên trường với nghề nghiệp IT",
    "slot_fill": "tư vấn thông tin nghề nghiệp IT",
}

CHAT_GREETING = (
    "Chào bạn! Mình là AI chuyên viên tư vấn hướng nghiệp IT. "
    "Mình có thể giúp bạn xây dựng lộ trình học tập, tìm kiếm khóa học phù hợp, "
    "hoặc giải đáp các kỹ năng cần thiết cho từng vị trí. "
    "Bạn đang quan tâm đến mảng nào trong ngành IT?"
)

OUT_OF_DOMAIN_MESSAGE = (
    "Xin lỗi bạn, mình được lập trình riêng để tư vấn về lộ trình nghề nghiệp "
    "và kỹ năng trong ngành IT nên không có thông tin về lĩnh vực này."
)

GENERATOR_OVERLOAD_MESSAGE = (
    "Hệ thống AI đang quá tải, bạn vui lòng thử lại sau ít giây nhé."
)

GENERATOR_NETWORK_MESSAGE = (
    "Kết nối đang chậm, mình thử lại giúp bạn nhé."
)

GENERATOR_UNKNOWN_ERROR_MESSAGE = (
    "Mình chưa trả lời được câu hỏi này lúc này. Bạn thử hỏi lại sau giây lát nhé."
)

SYSTEM_ERROR_INTENT = "_system_error"


def out_of_domain_message() -> str:
    return OUT_OF_DOMAIN_MESSAGE


def greeting_message() -> str:
    return CHAT_GREETING


def suggest_form_message() -> str:
    return (
        "Nếu bạn muốn được tư vấn về ngành IT, bạn có thể giúp mình điền form này "
        "để mình biết rõ hơn về bạn không?\n\n"
        "👉 Mở form tư vấn"
    )


def low_confidence_message(intent: Intent) -> str:
    label = _INTENT_LABELS.get(intent, "tư vấn nghề nghiệp IT")
    return (
        f"Bạn có đang hỏi về {label} trong lĩnh vực IT không?\n"
        "Bạn có thể nói rõ hơn được không?"
)


def profile_received_message() -> str:
    return (
        "Cảm ơn bạn đã điền form! Mình đã lưu hồ sơ của bạn. "
        "Bạn có thể tiếp tục hỏi trong khung chat — mình sẽ tư vấn dựa trên thông tin bạn cung cấp."
    )
