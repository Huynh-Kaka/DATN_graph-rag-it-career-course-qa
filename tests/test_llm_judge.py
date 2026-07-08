"""D-03 — unit tests LLM judge & citation proxy."""

import json

import pytest

from app.eval.llm_judge import (
    GeminiJudgeClient,
    GroqJudgeClient,
    LocalJudgeClient,
    OpenAIJudgeClient,
    _parse_judge_json,
    create_judge_client,
)
from app.generator.validator import count_course_citations


def test_parse_judge_json():
    text = json.dumps(
        {
            "faithfulness": 0.85,
            "skill_completeness": 0.7,
            "no_hallucination": True,
        }
    )
    scores = _parse_judge_json(text)
    assert scores.faithfulness == pytest.approx(0.85)
    assert scores.skill_completeness == pytest.approx(0.7)
    assert scores.no_hallucination is True


def test_parse_judge_json_clamps_range():
    scores = _parse_judge_json(
        '{"faithfulness": 1.5, "skill_completeness": -0.2, "no_hallucination": false}'
    )
    assert scores.faithfulness == 1.0
    assert scores.skill_completeness == 0.0


def test_count_course_citations_valid_and_invalid():
    graph = {
        "courses": [
            {"course_code": "CRS_LANG_L_PY_01"},
            {"course_code": "CRS_FRAM_F_REACT_01"},
        ]
    }
    text = "Xem [Course: CRS_LANG_L_PY_01] và [Course: FAKE_999]"
    stats = count_course_citations(text, graph_snapshot=graph)
    assert stats["n_citations"] == 2
    assert stats["n_valid_citations"] == 1
    assert stats["n_invalid_citations"] == 1


def test_gemini_judge_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(
        "app.eval.llm_judge.settings.judge_gemini_api_key",
        "",
    )
    client = GeminiJudgeClient()
    assert client.available is False


def test_openai_judge_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(
        "app.eval.llm_judge.settings.judge_openai_api_key",
        "",
    )
    client = OpenAIJudgeClient()
    assert client.available is False


def test_create_judge_client_gemini_default(monkeypatch):
    monkeypatch.setattr("app.eval.llm_judge.settings.judge_provider", "gemini")
    client = create_judge_client()
    assert isinstance(client, GeminiJudgeClient)


def test_create_judge_client_openai(monkeypatch):
    monkeypatch.setattr("app.eval.llm_judge.settings.judge_provider", "openai")
    client = create_judge_client()
    assert isinstance(client, OpenAIJudgeClient)


def test_groq_judge_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(
        "app.eval.llm_judge.settings.judge_groq_api_key",
        "",
    )
    client = GroqJudgeClient()
    assert client.available is False


def test_create_judge_client_groq(monkeypatch):
    monkeypatch.setattr("app.eval.llm_judge.settings.judge_provider", "groq")
    client = create_judge_client()
    assert isinstance(client, GroqJudgeClient)


def test_local_judge_unavailable_without_base_url(monkeypatch):
    monkeypatch.setattr("app.eval.llm_judge.settings.chatbot_local_base_url", "")
    client = LocalJudgeClient()
    assert client.available is False


def test_create_judge_client_local(monkeypatch):
    monkeypatch.setattr("app.eval.llm_judge.settings.judge_provider", "local")
    monkeypatch.setattr(
        "app.eval.llm_judge.settings.chatbot_local_base_url",
        "http://localhost:8081/v1",
    )
    from app.eval.llm_judge import FallbackJudgeClient

    client = create_judge_client()
    assert isinstance(client, FallbackJudgeClient)
    assert client.available is True


def test_fallback_judge_local_fail_groq_ok(monkeypatch):
    from app.eval.llm_judge import FallbackJudgeClient, JudgeScores

    class FailLocal:
        @property
        def available(self) -> bool:
            return True

        def score(self, **kwargs):
            raise RuntimeError("local down")

    class OkGroq:
        @property
        def available(self) -> bool:
            return True

        def score(self, **kwargs):
            return JudgeScores(0.9, 0.8, True)

    client = FallbackJudgeClient([("local", FailLocal()), ("groq", OkGroq())])
    result = client.score(
        question="q",
        answer="a",
        ground_truth={"expected_skills": []},
    )
    assert result.backend_used == "groq"
    assert result.faithfulness == pytest.approx(0.9)
