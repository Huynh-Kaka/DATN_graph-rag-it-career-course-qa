"""Contract tests: advisory normalization, dedupe, API response shape."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.advice.schema import normalize_advice_payload, normalize_skills_gap
from app.api.chat_routes import ChatResponse
from app.generator.advisory_prompt import (
    BACKGROUND_DISPLAY,
    build_advisory_user_prompt,
    format_advice_reply,
)
from app.response.api_shape import coerce_evidence, shape_chat_response
from app.response.structured import structured_from_advice
from app.services.advisory_service import AdvisoryService


def test_normalize_skills_gap_list():
    assert normalize_skills_gap(["Python", "SQL", ""]) == {
        "missing": ["Python", "SQL"],
        "weak": [],
        "soft_skills": [],
        "certifications": [],
    }


def test_normalize_skills_gap_mandatory_recommended_optional():
    gap = normalize_skills_gap(
        {
            "mandatory": ["Git"],
            "recommended": ["Docker"],
            "optional": ["Kubernetes"],
        }
    )
    assert gap["missing"] == ["Git", "Docker"]
    assert gap["weak"] == ["Kubernetes"]


def test_normalize_skills_gap_canonical_keys_win():
    gap = normalize_skills_gap(
        {"missing": ["A"], "weak": ["B"], "mandatory": ["ignored"]}
    )
    assert gap == {
        "missing": ["A"],
        "weak": ["B"],
        "soft_skills": [],
        "certifications": [],
    }


def test_normalize_skills_gap_non_dict_fallback():
    assert normalize_skills_gap(None) == {
        "missing": [],
        "weak": [],
        "soft_skills": [],
        "certifications": [],
    }
    assert normalize_skills_gap(42) == {
        "missing": [],
        "weak": [],
        "soft_skills": [],
        "certifications": [],
    }


def test_normalize_advice_payload_coerces_fields():
    raw = {
        "skills_gap": ["HTML"],
        "roadmap": [{"month": 1, "topics": ["CSS"], "milestone": "x"}],
        "recommended_courses": [{"title": "Web 101", "platform": "MOOC"}],
        "estimated_months": "8",
        "summary_vi": "  Tóm tắt  ",
    }
    out = normalize_advice_payload(raw)
    assert out["skills_gap"] == {
        "missing": ["HTML"],
        "weak": [],
        "soft_skills": [],
        "certifications": [],
    }
    assert len(out["roadmap"]) == 1
    assert out["estimated_months"] == 8
    assert out["summary_vi"] == "Tóm tắt"
    assert out["raw_response"] == "Tóm tắt"


def test_normalize_advice_payload_coerces_roadmap_month():
    out = normalize_advice_payload(
        {
            "roadmap": [
                {"milestone": "Landing page"},
                {"month": "2", "topics": ["React"], "milestone": "SPA"},
            ],
            "skills_gap": {"missing": [], "weak": []},
        }
    )
    assert out["roadmap"][0]["month"] == 1
    assert out["roadmap"][1]["month"] == 2
    assert out["roadmap"][1]["topics"] == ["React"]


def test_normalize_advice_payload_distributes_flat_courses_to_months():
    raw = {
        "roadmap": [
            {"month": 1, "topics": ["HTML"], "milestone": "Landing page"},
            {"month": 2, "topics": ["CSS"], "milestone": "Styled site"},
        ],
        "recommended_courses": [
            {"title": "Web 101", "platform": "Coursera", "url": "https://a.example"},
            {"title": "CSS Basics", "platform": "Udemy"},
        ],
        "skills_gap": {"missing": [], "weak": []},
    }
    out = normalize_advice_payload(raw)
    assert out["roadmap"][0]["courses"][0]["title"] == "Web 101"
    assert out["roadmap"][1]["courses"][0]["title"] == "CSS Basics"
    assert out["recommended_courses"][0]["title"] == "Web 101"


def test_normalize_advice_payload_coerces_roadmap_courses():
    out = normalize_advice_payload(
        {
            "roadmap": [
                {
                    "month": 1,
                    "topics": ["Python"],
                    "milestone": "Script",
                    "courses": [
                        {
                            "title": "Py 101",
                            "platform": "MOOC",
                            "url": "https://example.com/learn/py-101",
                        }
                    ],
                }
            ],
            "skills_gap": {"missing": [], "weak": []},
        }
    )
    assert out["roadmap"][0]["courses"][0]["url"] == "https://example.com/learn/py-101"


def test_structured_from_advice_embeds_courses_in_timeline():
    structured = structured_from_advice(
        {
            "roadmap": [
                {
                    "month": 1,
                    "topics": ["Git"],
                    "milestone": "Repo",
                    "courses": [{"title": "Git Pro", "platform": "Udemy"}],
                }
            ],
            "skills_gap": {"missing": [], "weak": []},
        },
        career="Backend",
    )
    timeline = next(s for s in structured.sections if s.type == "timeline")
    assert timeline.timeline[0]["courses"][0]["title"] == "Git Pro"
    assert not any(s.type == "courses" for s in structured.sections)


def test_plain_text_timeline_includes_month_courses():
    from app.response.structured import plain_text_from_structured, structured_from_advice

    structured = structured_from_advice(
        {
            "roadmap": [
                {
                    "month": 1,
                    "topics": ["React"],
                    "milestone": "App",
                    "courses": [
                        {
                            "title": "React Fundamentals",
                            "platform": "Coursera",
                            "url": "https://example.com/react",
                        }
                    ],
                }
            ],
            "skills_gap": {"missing": [], "weak": []},
        },
        career="Frontend Developer",
    )
    text = plain_text_from_structured(structured)
    assert "Tháng 1" in text
    assert "React Fundamentals" in text
    assert "Coursera" in text


def test_enrich_advice_roadmap_assigns_graph_courses():
    from unittest.mock import MagicMock

    from app.graph.course_suggestions import enrich_advice_roadmap
    from app.graph.models import CareerSkillCoursesResult, CourseItem, SkillCoursesBlock

    graph = MagicMock()
    graph.courses_for_career_skills.return_value = CareerSkillCoursesResult(
        found=True,
        blocks=[
            SkillCoursesBlock(
                competency_name="Python",
                courses=[
                    CourseItem(
                        course_name="Python for Everybody",
                        organization="Coursera",
                        url="https://example.com/py",
                    )
                ],
            )
        ],
    )
    roadmap = [
        {"month": 1, "topics": ["Python"], "milestone": "Basics", "courses": []},
    ]
    out = enrich_advice_roadmap(roadmap, ["Python"], graph, "Backend Developer")
    assert out[0]["courses"][0]["title"] == "Python for Everybody"
    assert out[0]["courses"][0]["url"] == "https://example.com/py"


def test_enrich_advice_roadmap_replaces_generic_platform_url():
    from unittest.mock import MagicMock

    from app.graph.course_suggestions import enrich_advice_roadmap
    from app.graph.models import CareerSkillCoursesResult, CourseItem, SkillCoursesBlock

    graph = MagicMock()
    graph.courses_for_career_skills.return_value = CareerSkillCoursesResult(
        found=True,
        blocks=[
            SkillCoursesBlock(
                competency_name="Python",
                courses=[
                    CourseItem(
                        course_name="Python Fundamentals",
                        organization="W3Schools",
                        url="https://www.w3schools.com/python/",
                    )
                ],
            )
        ],
    )
    roadmap = [
        {
            "month": 1,
            "topics": ["Python"],
            "milestone": "Basics",
            "courses": [
                {
                    "title": "Python Fundamentals",
                    "platform": "W3Schools",
                    "url": "https://www.w3schools.com",
                }
            ],
        },
    ]
    out = enrich_advice_roadmap(roadmap, ["Python"], graph, "Business Analyst")
    assert out[0]["courses"][0]["url"] == "https://www.w3schools.com/python/"


def test_enrich_advice_roadmap_prefers_graph_over_llm_wrong_platform():
    """Graph-first: LLM gắn Coursera Docker sai — lấy Udemy từ Neo4j."""
    from unittest.mock import MagicMock

    from app.graph.course_suggestions import enrich_advice_roadmap
    from app.graph.models import CareerSkillCoursesResult, CourseItem, SkillCoursesBlock

    graph = MagicMock()
    graph.courses_for_career_skills.return_value = CareerSkillCoursesResult(
        found=True,
        blocks=[
            SkillCoursesBlock(
                competency_name="Docker",
                courses=[
                    CourseItem(
                        course_name="Docker Platform Fundamentals",
                        organization="Udemy",
                        url="https://www.udemy.com/course/docker-and-kubernetes-the-complete-guide/",
                    )
                ],
            )
        ],
    )
    roadmap = [
        {
            "month": 3,
            "topics": ["DevOps", "Docker"],
            "milestone": "Container basics",
            "courses": [
                {
                    "title": "Docker Essentials",
                    "platform": "Coursera",
                    "url": "https://www.coursera.org/learn/docker",
                }
            ],
        },
    ]
    out = enrich_advice_roadmap(roadmap, [], graph, "DevOps Engineer")
    assert out[0]["courses"][0]["title"] == "Docker Platform Fundamentals"
    assert "udemy.com" in out[0]["courses"][0]["url"]


def test_enrich_advice_skills_gap_adds_soft_and_cert():
    from unittest.mock import MagicMock

    from app.graph.course_suggestions import enrich_advice_skills_gap
    from app.graph.models import CompetencyItem, PathfindingResult

    graph = MagicMock()

    def _pf(career, rel, *, known_skills=None, **kwargs):
        if rel == "NEED_SOFT":
            return PathfindingResult(
                found=True,
                competencies=[
                    CompetencyItem(name="Communication", code="S_COMM", kind="Softskill"),
                    CompetencyItem(name="Collaboration", code="S_COLLAB", kind="Softskill"),
                ],
                skills_missing=[
                    CompetencyItem(name="Communication", code="S_COMM", kind="Softskill")
                ],
            )
        if rel == "NEED_CERT":
            return PathfindingResult(
                found=True,
                competencies=[
                    CompetencyItem(
                        name="AWS Cloud Practitioner", code="C_AWS_CP", kind="Certification"
                    )
                ],
                skills_missing=[
                    CompetencyItem(
                        name="AWS Cloud Practitioner", code="C_AWS_CP", kind="Certification"
                    )
                ],
            )
        return PathfindingResult(found=False)

    graph.pathfinding_by_type.side_effect = _pf
    out = enrich_advice_skills_gap(
        {"skills_gap": {"missing": ["Python"], "weak": []}},
        graph,
        "Backend Developer",
        known_skills=["python"],
    )
    gap = out["skills_gap"]
    assert "Communication" in gap["soft_skills"]
    assert "AWS Cloud Practitioner" in gap["certifications"]


def test_is_generic_site_url():
    from app.advice.schema import is_generic_site_url

    assert is_generic_site_url("https://www.coursera.org")
    assert is_generic_site_url("https://www.w3schools.com/")
    assert not is_generic_site_url("https://www.coursera.org/learn/data-analysis-with-python")
    assert not is_generic_site_url("https://www.w3schools.com/python/")


def test_plain_text_timeline_and_courses():
    from app.response.structured import plain_text_from_structured, structured_from_advice

    structured = structured_from_advice(
        {
            "roadmap": [
                {"milestone": "Portfolio"},
                {"month": 2, "topics": ["React"], "milestone": "App"},
            ],
            "recommended_courses": [
                {
                    "title": "Web Fundamentals",
                    "platform": "Coursera",
                    "url": "https://example.com/course",
                }
            ],
            "skills_gap": {"missing": [], "weak": []},
        },
        career="Frontend Developer",
    )
    text = plain_text_from_structured(structured)
    assert "Tháng 1" in text
    assert "Portfolio" in text
    assert "Tháng 2: React" in text
    assert "Web Fundamentals" in text
    assert "Coursera" in text
    assert "Tháng None" not in text


def test_normalize_advice_payload_invalid_nested_ignored():
    out = normalize_advice_payload(
        {
            "skills_gap": {"mandatory": ["Go"]},
            "roadmap": "not-a-list",
            "recommended_courses": None,
            "estimated_months": "n/a",
        }
    )
    assert out["skills_gap"]["missing"] == ["Go"]
    assert out["roadmap"] == []
    assert out["recommended_courses"] == []
    assert out["estimated_months"] is None


def test_structured_from_advice_accepts_variant_skills_gap():
    structured = structured_from_advice(
        {"skills_gap": {"mandatory": ["Python"], "optional": ["Linux"]}},
        career="Backend",
        known_skills=["sql"],
    )
    gap_sec = next(s for s in structured.sections if s.type == "skills_gap")
    assert "Python" in gap_sec.chips_missing
    assert "Linux" in gap_sec.chips_weak


def test_format_advice_reply_uses_normalized_gap():
    text = format_advice_reply(
        {"skills_gap": ["Rust"], "estimated_months": 4, "summary_vi": ""}
    )
    assert "Rust" in text
    assert "4" in text


def test_advisory_prompt_imports_and_background_display():
    assert "Sinh viên" in BACKGROUND_DISPLAY.values() or BACKGROUND_DISPLAY
    profile = SimpleNamespace(
        background="student",
        role="backend",
        role_note=None,
        known_skills=["python"],
        weekly_time="5to10",
        goals=["roadmap"],
        initial_question=None,
    )
    prompt = build_advisory_user_prompt(profile, graph_context=["ctx"])
    assert "known_skills" in prompt
    assert "ctx" in prompt


def test_coerce_evidence_rejects_list():
    assert coerce_evidence([]) == {}
    assert coerce_evidence({"chunk_ids": ["c1"]}) == {"chunk_ids": ["c1"]}
    assert coerce_evidence(None) is None


def test_shape_chat_response_evidence_for_chat_response_model():
    shaped = shape_chat_response(
        {
            "session_id": "s1",
            "reply": "ok",
            "evidence": [],
        }
    )
    resp = ChatResponse(**shaped)
    assert resp.evidence == {}


def test_assistant_reply_exists_dedupes_last_assistant():
    state = SimpleNamespace(
        messages=[
            SimpleNamespace(role="user", content="hi"),
            SimpleNamespace(role="assistant", content="Same reply"),
        ]
    )
    assert AdvisoryService._assistant_reply_exists(state, "Same reply") is True
    assert AdvisoryService._assistant_reply_exists(state, "Different") is False


def test_assistant_reply_exists_empty_content_treated_as_present():
    state = SimpleNamespace(messages=[])
    assert AdvisoryService._assistant_reply_exists(state, "") is True
    assert AdvisoryService._assistant_reply_exists(state, "   ") is True
