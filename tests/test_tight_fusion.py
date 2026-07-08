"""Tests cho A-01 — Tight Fusion (vector hits → graph seed nodes)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from app.graph.models import (
    CompetencyItem,
    CourseItem,
    CourseRecResult,
    PathfindingResult,
)
from app.graph.queries.course_rec import fetch_course_recommendations
from app.graph.queries.pathfinding import _CYPHER, _parse_skills, fetch_pathfinding
from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome
from app.rag.fusion import FusionService, map_hits_to_graph_nodes
from app.rag.retriever import RetrievedDoc


# ---------- map_hits_to_graph_nodes ----------


def test_map_hits_career_payload():
    hits = [
        RetrievedDoc(
            text="Backend Developer ...",
            score=0.9,
            payload={
                "doc_type": "career",
                "canonical_id": "BE",
                "career_code": "BE",
                "career_name": "Backend Developer",
            },
        )
    ]
    seed = map_hits_to_graph_nodes(hits)
    assert seed["career_codes"] == ["BE"]
    assert seed["competency_codes"] == []
    assert seed["course_codes"] == []


def test_map_hits_competency_and_course_payload():
    hits = [
        RetrievedDoc(
            text="Python ...",
            score=0.8,
            payload={
                "doc_type": "competency",
                "canonical_id": "L_PY",
                "item_code": "L_PY",
                "item_name": "Python",
                "kind": "ProgrammingLanguage",
            },
        ),
        RetrievedDoc(
            text="Course Python ...",
            score=0.7,
            payload={
                "doc_type": "course",
                "canonical_id": "PY101",
                "course_code": "PY101",
                "course_name": "Python for AI",
                "competencies": [{"item_code": "L_PY"}, "L_SQL"],
            },
        ),
    ]
    seed = map_hits_to_graph_nodes(hits)
    assert seed["competency_codes"] == ["L_PY", "L_SQL"]
    assert seed["course_codes"] == ["PY101"]
    assert seed["career_codes"] == []


def test_map_hits_handles_none_and_strings_and_dedup():
    hits = [
        RetrievedDoc(
            text="x",
            score=0.1,
            payload={"doc_type": "career", "canonical_id": "BE", "career_code": "BE"},
        ),
        RetrievedDoc(
            text="x",
            score=0.1,
            payload={"doc_type": "career", "canonical_id": "BE", "career_code": "BE"},
        ),
        "not a doc, just a string",  # type: ignore[list-item]
    ]
    seed = map_hits_to_graph_nodes(hits)  # type: ignore[arg-type]
    assert seed["career_codes"] == ["BE"]

    empty = map_hits_to_graph_nodes(None)
    assert empty == {"career_codes": [], "competency_codes": [], "course_codes": []}


# ---------- FusionService.aggregate with seed_ids ----------


def test_fusion_aggregate_emits_seed_ids_in_context_and_evidence():
    fusion = FusionService()
    docs = [
        RetrievedDoc(
            text="Backend snippet",
            score=0.9,
            payload={
                "doc_type": "career",
                "canonical_id": "BE",
                "career_code": "BE",
                "chunk_id": "c1",
            },
        )
    ]
    out = fusion.aggregate(
        graph_payload={"found": True, "career_name": "Backend Developer", "career_code": "BE"},
        vector_docs=docs,
    )
    assert "Seed nodes (vector→graph)" in out["context_block"]
    assert out["graph_seed_ids"]["career_codes"] == ["BE"]
    assert out["evidence"]["graph_seed_ids"]["career_codes"] == ["BE"]
    assert "c1" in out["evidence"]["chunk_ids"]


def test_fusion_aggregate_explicit_seed_ids_overrides_inference():
    fusion = FusionService()
    out = fusion.aggregate(
        graph_payload={"found": True, "career_name": "X"},
        vector_docs=[],
        graph_seed_ids={"career_codes": ["BE"], "competency_codes": ["L_PY"], "course_codes": []},
    )
    assert out["graph_seed_ids"]["competency_codes"] == ["L_PY"]
    assert "competency=L_PY" in out["context_block"]


# ---------- Cypher binding: seed codes are forwarded ----------


def _stub_neo4j_client_with_row(row: dict | None) -> MagicMock:
    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.available = True
    client.session.return_value.__enter__.return_value = session
    client.session.return_value.__exit__.return_value = False
    return client, session


def test_cypher_career_name_ranked_above_seed_codes():
    """Tên career từ intent phải thắng seed_career_codes (tránh chọn sai nghề)."""
    assert "toLower(trim(c.career_name)) = toLower(trim($career)) THEN 0" in _CYPHER
    seed_pos = _CYPHER.index("c.career_code IN $seed_career_codes")
    name_pos = _CYPHER.index("toLower(trim(c.career_name)) = toLower(trim($career))")
    assert name_pos < seed_pos


def test_fetch_pathfinding_passes_seed_codes_to_cypher():
    row = {
        "career_name": "Backend Developer",
        "career_code": "BE",
        "industry": "SE",
        "skills": [
            {"name": "Python", "kind": "ProgrammingLanguage", "code": "L_PY", "priority": 1, "is_seed": True},
            {"name": "SQL", "kind": "ProgrammingLanguage", "code": "L_SQL", "priority": 2, "is_seed": False},
        ],
    }
    client, session = _stub_neo4j_client_with_row(row)
    result = fetch_pathfinding(
        client,
        "Backend Developer",
        seed_career_codes=["BE"],
        seed_competency_codes=["L_PY"],
    )

    assert result.found is True
    # Seed competency must be sorted to the top.
    assert result.competencies[0].name == "Python"
    assert result.competencies[0].is_seed is True

    session.run.assert_called_once()
    kwargs = session.run.call_args.kwargs
    assert kwargs["career"] == "Backend Developer"
    assert kwargs["seed_career_codes"] == ["BE"]
    assert kwargs["seed_competency_codes"] == ["L_PY"]


def test_fetch_pathfinding_without_seed_codes_keeps_backward_compat():
    row = {
        "career_name": "Data Analyst",
        "career_code": "DA",
        "industry": "Analytics",
        "skills": [
            {"name": "Python", "kind": "ProgrammingLanguage", "code": "L_PY", "priority": 1},
        ],
    }
    client, session = _stub_neo4j_client_with_row(row)
    result = fetch_pathfinding(client, "Data Analyst")
    assert result.found is True
    kwargs = session.run.call_args.kwargs
    assert kwargs["seed_career_codes"] is None
    assert kwargs["seed_competency_codes"] is None


def test_parse_skills_orders_is_seed_first():
    raw = [
        {"name": "SQL", "kind": "ProgrammingLanguage", "code": "L_SQL", "is_seed": False, "priority": 1},
        {"name": "Python", "kind": "ProgrammingLanguage", "code": "L_PY", "is_seed": True, "priority": 2},
        {"name": "Git", "kind": "Tool", "code": "T_GIT", "is_seed": False, "priority": 1},
    ]
    items = _parse_skills(raw)
    # is_seed=True luôn đứng đầu, sau đó sort theo (kind, name).
    assert items[0].name == "Python"
    assert items[0].is_seed is True


# ---------- Course rec: seed codes ----------


def test_fetch_course_recommendations_passes_seed_codes():
    row = {
        "competency_name": "Python",
        "competency_kind": "ProgrammingLanguage",
        "courses": [
            {"course_name": "Python 101", "course_code": "PY101", "is_seed": False},
            {"course_name": "Python for AI", "course_code": "PY-AI", "is_seed": True},
        ],
    }
    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.available = True
    client.competency_labels.return_value = ("ProgrammingLanguage",)
    client.session.return_value.__enter__.return_value = session
    client.session.return_value.__exit__.return_value = False

    result = fetch_course_recommendations(
        client, "Python", seed_course_codes=["PY-AI"]
    )

    assert result.found is True
    # is_seed boost: PY-AI lên đầu.
    assert result.courses[0].course_code == "PY-AI"
    assert result.courses[0].is_seed is True

    kwargs = session.run.call_args.kwargs
    assert kwargs["needle"] == "Python"
    assert kwargs["seed_course_codes"] == ["PY-AI"]


# ---------- Integration: ChatService wires seed_ids into GraphRepository ----------


class _StubSessions:
    def __init__(self) -> None:
        from app.session.store import SessionState

        # phase="course" để bypass nhánh competency_flow trong _answer_from_intent
        # (test này tập trung vào nhánh pathfinding chuẩn).
        self._state = SessionState(
            session_id="s1", career="Backend Developer", phase="course"
        )
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
    def route(self, message, *, user_prompt=None, state=None):
        return RouteOutcome(
            route=IntentRouteResult(
                domain="in",
                intent="pathfinding",
                confidence="high",
                entities=IntentEntities(career="Backend Developer"),
            ),
            stop=False,
            reply=None,
        )


class _StubExemplars:
    async def fetch_examples(self, query, *, top_k=2):
        return []


class _CapturingGraph:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def pathfinding(self, career, *, known_skills=None, **kwargs):
        self.calls.append({"career": career, **kwargs})
        return PathfindingResult(
            found=True,
            career_name=career,
            career_code="BE",
            competencies=[
                CompetencyItem(
                    name="Python", kind="ProgrammingLanguage", code="L_PY", is_seed=True
                ),
            ],
        )

    def course_recommendation(self, competency, *, seed_course_codes=None):
        self.calls.append({"competency": competency, "seed_course_codes": seed_course_codes})
        return CourseRecResult(
            found=True,
            competency_name=competency,
            competency_kind="ProgrammingLanguage",
            courses=[
                CourseItem(course_name="Python 101", course_code="PY101", is_seed=False),
            ],
        )


class _StubRetriever:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def retrieve_docs(self, message, top_k=3, *, doc_type=None, relevant_ids=None):
        self.calls.append(
            {"message": message, "top_k": top_k, "doc_type": doc_type, "relevant_ids": relevant_ids}
        )
        return [
            RetrievedDoc(
                text="Backend Developer ...",
                score=0.9,
                payload={
                    "doc_type": "career",
                    "canonical_id": "BE",
                    "career_code": "BE",
                    "chunk_id": "c-be",
                },
            ),
            RetrievedDoc(
                text="Python ...",
                score=0.8,
                payload={
                    "doc_type": "competency",
                    "canonical_id": "L_PY",
                    "item_code": "L_PY",
                    "chunk_id": "c-py",
                },
            ),
        ]


class _StubGenerator:
    last_generator_backend = "stub"

    def pathfinding(self, *, user_message, result, state, vector_context, exemplars, route_confidence, **kwargs):
        # Verify that tight-fusion context_block reaches the generator.
        self._last_context = vector_context
        return f"reply: {result.career_name}"

    def slot_fill(self, *, user_message, route, state, fallback):
        return fallback


def test_chat_service_pathfinding_forwards_seed_ids_to_graph_and_fusion():
    """End-to-end wiring: vector hits → seed_map → GraphRepository.pathfinding."""

    from app.services.chat_service import ChatService

    sessions = _StubSessions()
    graph = _CapturingGraph()
    generator = _StubGenerator()

    retriever = _StubRetriever()
    svc = ChatService(
        sessions=sessions,
        router=_StubRouter(),
        graph=graph,  # type: ignore[arg-type]
        generator=generator,  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        exemplars=_StubExemplars(),  # type: ignore[arg-type]
    )

    result = asyncio.run(svc.handle_message(message="Tôi muốn làm backend", session_id="s1"))

    # A-03: retrieve lần 2 với relevant_ids từ subgraph Neo4j.
    assert len(retriever.calls) == 2
    assert retriever.calls[1]["relevant_ids"] is not None
    assert "BE" in retriever.calls[1]["relevant_ids"]

    # Graph.pathfinding nhận đúng seed codes do vector retriever trả về.
    assert graph.calls, "GraphRepository.pathfinding must be invoked"
    call = graph.calls[0]
    assert call["seed_career_codes"] == ["BE"]
    assert call["seed_competency_codes"] == ["L_PY"]

    # Evidence trong reply có graph_seed_ids (A-01 trace).
    evidence = result.get("evidence") or {}
    assert evidence.get("graph_seed_ids", {}).get("career_codes") == ["BE"]
    assert evidence.get("graph_seed_ids", {}).get("competency_codes") == ["L_PY"]

    # Context block tới generator có dòng "Seed nodes" — chứng tỏ tight fusion đã wire.
    assert "Seed nodes" in getattr(generator, "_last_context", "")
