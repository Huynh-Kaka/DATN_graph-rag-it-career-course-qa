from unittest.mock import MagicMock

from app.eval.ablation_pipeline import AblationPipeline, FusionMode
from app.graph.models import CompetencyItem, PathfindingResult
from app.rag.retriever import RetrievedDoc


class _StubGraph:
    def __init__(self) -> None:
        self.last_seed_career: list[str] | None = None
        self.last_seed_comp: list[str] | None = None

    def pathfinding(self, career, *, known_skills=None, seed_career_codes=None, seed_competency_codes=None):
        self.last_seed_career = list(seed_career_codes or [])
        self.last_seed_comp = list(seed_competency_codes or [])
        return PathfindingResult(
            found=True,
            career_name=career,
            career_code="BE",
            competencies=[
                CompetencyItem(name="Python", kind="ProgrammingLanguage", is_seed=True),
                CompetencyItem(name="SQL", kind="ProgrammingLanguage"),
            ],
        )

    def course_recommendation(self, competency, *, seed_course_codes=None):
        return MagicMock(found=False, model_dump=lambda: {})

    def competency_relations(self, competency, **kwargs):
        from app.graph.models import CompetencyRelationEdge, CompetencyRelationResult

        return CompetencyRelationResult(
            found=True,
            coverage="full",
            anchor_name="React",
            anchor_code="F_REACT",
            outgoing=[
                CompetencyRelationEdge(
                    rel_type="BUILT_ON",
                    from_code="F_REACT",
                    from_name="React",
                    to_code="L_JS",
                    to_name="JavaScript",
                )
            ],
        )

    def close(self):
        pass


class _StubRetriever:
    def retrieve_docs(self, query, top_k=3, *, doc_type=None):
        if doc_type == "career":
            return [
                RetrievedDoc(
                    text="Backend Developer Python",
                    score=0.9,
                    payload={
                        "doc_type": "career",
                        "canonical_id": "BE",
                        "career_code": "BE",
                        "title": "Backend Developer",
                    },
                ),
                RetrievedDoc(
                    text="Python competency",
                    score=0.8,
                    payload={
                        "doc_type": "competency",
                        "canonical_id": "L_PY",
                        "item_code": "L_PY",
                        "item_name": "Python",
                    },
                ),
            ]
        return []


def test_tight_fusion_passes_seed_codes_to_graph():
    graph = _StubGraph()
    pipe = AblationPipeline(graph=graph, retriever=_StubRetriever())
    item = {
        "id": "t1",
        "intent": "pathfinding",
        "query": "Backend cần học gì?",
        "career": "Backend Developer",
        "gold_skills": ["Python", "SQL"],
    }
    result = pipe.run_case(item, FusionMode.TIGHT_FUSION)
    assert graph.last_seed_career == ["BE"]
    assert "L_PY" in graph.last_seed_comp
    assert result.scores.skill_accuracy == 1.0
    pipe.close()


def test_graph_only_does_not_use_seeds():
    graph = _StubGraph()
    pipe = AblationPipeline(graph=graph, retriever=_StubRetriever())
    item = {
        "id": "t2",
        "intent": "pathfinding",
        "query": "Backend cần học gì?",
        "career": "Backend Developer",
        "gold_skills": ["Python"],
    }
    pipe.run_case(item, FusionMode.GRAPH_ONLY)
    assert graph.last_seed_career == []
    assert graph.last_seed_comp == []
    pipe.close()


def test_late_fusion_static_appends_vector_context():
    graph = _StubGraph()
    pipe = AblationPipeline(graph=graph, retriever=_StubRetriever())
    item = {
        "id": "t_late",
        "intent": "pathfinding",
        "query": "Backend cần học gì?",
        "career": "Backend Developer",
        "gold_skills": ["Python"],
    }
    result = pipe.run_case(item, FusionMode.LATE_FUSION)
    assert "Ngữ cảnh vector retrieval" in result.reply
    assert result.vector_doc_count >= 1
    pipe.close()


def test_vector_only_skips_graph():
    graph = _StubGraph()
    pipe = AblationPipeline(graph=graph, retriever=_StubRetriever())
    item = {
        "id": "t3",
        "intent": "pathfinding",
        "query": "Backend cần học gì?",
        "career": "Backend Developer",
        "gold_skills": ["Python"],
    }
    result = pipe.run_case(item, FusionMode.VECTOR_ONLY)
    assert result.graph is None
    assert result.vector_doc_count >= 1
    assert "vector retrieval" in result.reply.lower()
    pipe.close()


def test_competency_relation_graph_only():
    graph = _StubGraph()
    pipe = AblationPipeline(graph=graph, retriever=_StubRetriever())
    item = {
        "id": "t_rel",
        "intent": "competency_relation",
        "query": "React cần học gì trước?",
        "competency": "React",
        "gold_related_codes": ["L_JS"],
    }
    result = pipe.run_case(item, FusionMode.GRAPH_ONLY)
    assert result.intent == "competency_relation"
    assert result.scores.relation_code_recall == 1.0
    assert "L_JS" in result.reply or "JavaScript" in result.reply
    pipe.close()
