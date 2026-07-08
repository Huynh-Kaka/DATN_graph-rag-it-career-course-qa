"""Tests phase idle vs pathfinding hijack (fix competency flow false start)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.graph.models import CompetencyItem, PathfindingResult
from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome
from app.services.chat_service import ChatService
from app.services.competency_orchestrator import CompetencyTypeOrchestrator
from app.session.store import SessionState
from app.db.repository import _coerce_phase


class _StubSessions:
    def __init__(self, state: SessionState) -> None:
        self._state = state
        self.saved = 0

    async def get_or_create(self, sid):
        return self._state

    async def save(self, state):
        self.saved += 1

    async def append_message(self, state, role, content, *, route_meta=None):
        return f"msg-{role}"

    async def list_messages(self, sid, *, limit=50):
        return []

    async def list_sessions(self, *, limit=20):
        return []


class _StubRouter:
    def __init__(self, *, intent: str, career: str | None = None) -> None:
        self._intent = intent
        self._career = career

    def route(self, message, *, user_prompt=None, state=None):
        return RouteOutcome(
            route=IntentRouteResult(
                domain="in",
                intent=self._intent,  # type: ignore[arg-type]
                confidence="high",
                entities=IntentEntities(career=self._career),
            ),
            stop=False,
            reply=None,
        )


class _CapturingGraph:
    def __init__(self) -> None:
        self.pathfinding_calls: list[dict] = []
        self.start_collection_calls = 0

    def pathfinding(self, career, *, known_skills=None, **kwargs):
        self.pathfinding_calls.append(
            {"career": career, "known_skills": known_skills, **kwargs}
        )
        return PathfindingResult(
            found=True,
            career_name=str(career),
            career_code="BE",
            competencies=[
                CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
            ],
        )

    def pathfinding_by_type(self, career, rel_type, *, known_skills=None):
        if rel_type == "NEED_LANG":
            return PathfindingResult(
                found=True,
                career_name=career,
                competencies=[
                    CompetencyItem(name="Python", kind="ProgrammingLanguage"),
                ],
            )
        return PathfindingResult(found=True, career_name=career, competencies=[])

    def course_recommendation(self, *args, **kwargs):
        return MagicMock(found=False, courses=[])


class _StubRetriever:
    def retrieve_docs(self, message, top_k=3, *, doc_type=None, relevant_ids=None):
        return []


class _StubExemplars:
    async def fetch_examples(self, query, *, top_k=2):
        return []


class _StubGenerator:
    last_generator_backend = "stub"

    def pathfinding(self, **kwargs):
        return "pathfinding reply"

    def slot_fill(self, **kwargs):
        return kwargs.get("fallback", "")


def _make_service(
    state: SessionState,
    *,
    intent: str = "pathfinding",
    career: str | None = None,
) -> tuple[ChatService, _CapturingGraph]:
    graph = _CapturingGraph()
    svc = ChatService(
        sessions=_StubSessions(state),
        router=_StubRouter(intent=intent, career=career),
        graph=graph,  # type: ignore[arg-type]
        generator=_StubGenerator(),  # type: ignore[arg-type]
        retriever=_StubRetriever(),  # type: ignore[arg-type]
        exemplars=_StubExemplars(),  # type: ignore[arg-type]
    )
    return svc, graph


def test_coerce_phase_legacy_collecting_orphan_to_idle():
    assert _coerce_phase("collecting", index=0, known_by_type={}) == "idle"
    assert _coerce_phase("collecting", index=2, known_by_type={}) == "collecting"
    assert _coerce_phase("collecting", index=0, known_by_type={"CT_LANG": ["Python"]}) == "collecting"
    assert _coerce_phase(None) == "idle"
    assert _coerce_phase("idle") == "idle"


def test_idle_pathfinding_no_question_mark_uses_graph():
    state = SessionState(session_id="idle-pf", phase="idle")
    svc, graph = _make_service(
        state, intent="pathfinding", career="DevOps Engineer"
    )
    result = asyncio.run(
        svc.handle_message(message="DevOps Engineer roadmap", session_id="idle-pf")
    )
    assert graph.pathfinding_calls, "pathfinding must be called from idle session"
    assert "Bước 1/7" not in result.get("reply", "")
    assert result.get("route", {}).get("intent") == "pathfinding"


def test_idle_pathfinding_with_question_mark_uses_graph():
    state = SessionState(session_id="idle-q", phase="idle")
    svc, graph = _make_service(
        state, intent="pathfinding", career="Data Scientist"
    )
    result = asyncio.run(
        svc.handle_message(
            message="Lộ trình Data Scientist cần học những gì?",
            session_id="idle-q",
        )
    )
    assert graph.pathfinding_calls
    assert result.get("route", {}).get("intent") == "pathfinding"


def test_collecting_same_career_pathfinding_uses_graph():
    state = SessionState(
        session_id="coll-same",
        career="Backend Developer",
        phase="collecting",
        competency_type_index=2,
        known_by_type={"CT_LANG": ["Python"]},
    )
    svc, graph = _make_service(
        state, intent="pathfinding", career="Backend Developer"
    )
    result = asyncio.run(
        svc.handle_message(message="Backend roadmap", session_id="coll-same")
    )
    assert graph.pathfinding_calls
    assert "Bước 1/7" not in result.get("reply", "")
    assert result.get("route", {}).get("intent") == "pathfinding"


def test_collecting_career_switch_restarts_seven_step_flow():
    state = SessionState(
        session_id="coll-switch",
        career="Backend Developer",
        phase="collecting",
        competency_type_index=2,
        known_by_type={"CT_LANG": ["Python"]},
    )
    svc, graph = _make_service(
        state, intent="pathfinding", career="Frontend Developer"
    )
    result = asyncio.run(
        svc.handle_message(
            message="Frontend Developer roadmap",
            session_id="coll-switch",
        )
    )
    assert not graph.pathfinding_calls
    assert "Bước 1/7" in result.get("reply", "")
    assert result.get("route", {}).get("intent") == "competency_slot_fill"
    assert state.phase == "collecting"
    assert state.competency_type_index == 0
    assert state.known_by_type == {}


def test_gap_summary_new_career_pathfinding_clears_skills():
    state = SessionState(
        session_id="gap-switch",
        career="Backend Developer",
        phase="gap_summary",
        competency_type_index=7,
        known_by_type={"CT_LANG": ["Python"], "CT_FRAM": ["Django"]},
    )
    svc, graph = _make_service(
        state, intent="pathfinding", career="Frontend Developer"
    )
    result = asyncio.run(
        svc.handle_message(
            message="Frontend Developer roadmap",
            session_id="gap-switch",
        )
    )
    assert graph.pathfinding_calls
    assert state.known_by_type == {}
    assert state.phase == "idle"
    assert state.competency_type_index == 0
    assert "Bước 1/7" not in result.get("reply", "")
    assert result.get("route", {}).get("intent") == "pathfinding"


class _StubGraphForOrch:
    def pathfinding_by_type(self, career: str, rel_type: str, *, known_skills=None):
        if rel_type == "NEED_LANG":
            return PathfindingResult(
                found=True,
                career_name=career,
                competencies=[
                    CompetencyItem(name="Python", kind="ProgrammingLanguage"),
                    CompetencyItem(name="SQL", kind="ProgrammingLanguage"),
                ],
            )
        if rel_type == "NEED_FRAM":
            return PathfindingResult(
                found=True,
                career_name=career,
                competencies=[
                    CompetencyItem(name="React", kind="Framework"),
                ],
            )
        return PathfindingResult(found=True, career_name=career, competencies=[])


def test_idle_competency_slot_fill_with_skills_advances_without_start_collection():
    state = SessionState(session_id="idle-skills", career="Data Analyst", phase="idle")
    orch = CompetencyTypeOrchestrator(graph=_StubGraphForOrch())
    turn = orch.handle_turn(state, "Python, SQL")
    assert turn.handled
    assert state.phase == "collecting"
    assert "Python" in state.known_by_type.get("CT_LANG", [])
    assert state.competency_type_index >= 1
    assert turn.structured and turn.structured.get("step", 0) >= 2


def test_idle_competency_slot_fill_no_skills_shows_step_one_card():
    state = SessionState(session_id="idle-empty", career="Data Analyst", phase="idle")
    orch = CompetencyTypeOrchestrator(graph=_StubGraphForOrch())
    turn = orch.handle_turn(state, "bắt đầu khai báo kỹ năng")
    assert turn.handled
    assert state.phase == "collecting"
    assert turn.structured and turn.structured.get("step") == 1
    assert turn.structured.get("type") == "competency_collection"
