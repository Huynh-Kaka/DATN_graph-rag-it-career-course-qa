"""A-03 — Graph-aware re-ranking (relevant_ids boost)."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.graph.models import (
    CompetencyItem,
    CourseItem,
    CourseRecResult,
    PathfindingResult,
)
from app.rag.fusion import extract_relevant_ids_from_graph
from app.rag.retriever import (
    RetrievedDoc,
    VectorRetriever,
    _apply_graph_boost,
    _invalidate_bm25_cache,
)

# Đa dạng ngành nghề từ retrieval_gold (63 career) — không chỉ Backend Developer.
CAREER_CORPUS = [
    (
        "DS",
        "Data Scientist",
        "Data Scientist statistics machine learning python pandas",
    ),
    (
        "GD",
        "Game Developer",
        "Game Developer unity c# game engine graphics gameplay",
    ),
    (
        "DO",
        "DevOps Engineer",
        "DevOps Engineer docker kubernetes ci cd infrastructure",
    ),
    (
        "BI",
        "BI Analyst",
        "BI Analyst power bi tableau sql reporting dashboard",
    ),
    (
        "MLE",
        "Machine Learning Engineer",
        "Machine Learning Engineer tensorflow pytorch mlops deployment",
    ),
    (
        "BC",
        "Blockchain Developer",
        "Blockchain Developer solidity web3 smart contract ethereum",
    ),
    (
        "ARVR",
        "AR/VR Developer",
        "AR VR Developer unity 3d immersive reality headset",
    ),
    (
        "FE",
        "Frontend Developer",
        "Frontend Developer react css html javascript ui",
    ),
]


def _bm25_rows() -> list[tuple[str, str, dict]]:
    rows: list[tuple[str, str, dict]] = []
    for code, name, text in CAREER_CORPUS:
        rows.append(
            (
                code,
                name,
                {
                    "doc_id": code,
                    "chunk_id": code,
                    "canonical_id": code,
                    "career_code": code,
                    "career_name": name,
                    "title": name,
                    "text": text,
                    "doc_type": "career",
                },
            )
        )
    rows.append(
        (
            "PY101",
            "Python for Data Science",
            {
                "doc_id": "PY101",
                "chunk_id": "PY101",
                "canonical_id": "PY101",
                "course_code": "PY101",
                "course_name": "Python for Data Science",
                "title": "Python for Data Science",
                "text": "Python pandas numpy data science course",
                "doc_type": "course",
            },
        )
    )
    return rows


def test_apply_graph_boost_adds_exact_configured_delta(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_graph_boost", 0.15)
    doc = RetrievedDoc(
        text="Python course",
        score=0.02,
        payload={"canonical_id": "PY101", "course_code": "PY101"},
    )
    out = _apply_graph_boost([doc], {"PY101"})
    assert len(out) == 1
    assert out[0].score == pytest.approx(0.02 + 0.15)


def test_apply_graph_boost_noop_when_relevant_ids_empty():
    doc = RetrievedDoc("x", 0.5, {"canonical_id": "DS"})
    assert _apply_graph_boost([doc], None)[0].score == 0.5
    assert _apply_graph_boost([doc], set())[0].score == 0.5


@pytest.mark.parametrize(
    "target_code,target_name,query,distractor_code",
    [
        ("DS", "Data Scientist", "muốn theo nghề data scientist", "FE"),
        ("GD", "Game Developer", "lộ trình game developer", "FE"),
        ("DO", "DevOps Engineer", "học devops cần gì", "FE"),
        ("BI", "BI Analyst", "BI analyst cần học gì", "FE"),
        ("MLE", "Machine Learning Engineer", "machine learning engineer lộ trình", "FE"),
        ("BC", "Blockchain Developer", "muốn làm blockchain", "FE"),
        ("ARVR", "AR/VR Developer", "làm AR VR developer", "FE"),
    ],
)
def test_hybrid_rerank_promotes_graph_subgraph_career(
    target_code: str,
    target_name: str,
    query: str,
    distractor_code: str,
):
    """Vector ưu tiên nhầm FE; boost subgraph đưa đúng career lên top."""
    _invalidate_bm25_cache()
    corpus = _bm25_rows()
    by_code = {row[0]: row[2] for row in corpus}

    retriever = VectorRetriever()
    retriever.set_bm25_corpus(corpus)

    vector_docs = [
        RetrievedDoc(
            text=by_code[distractor_code]["text"],
            score=0.99,
            payload=by_code[distractor_code],
        )
    ]
    out_plain = retriever._hybrid_rerank(query, vector_docs, top_k=1)
    out_boost = retriever._hybrid_rerank(
        query,
        vector_docs,
        top_k=1,
        relevant_ids={target_code},
    )

    assert out_plain[0].payload["career_name"] != target_name
    assert out_boost[0].payload["career_name"] == target_name
    assert out_boost[0].payload["canonical_id"] == target_code


def test_hybrid_rerank_course_code_boost():
    _invalidate_bm25_cache()
    corpus = _bm25_rows()
    retriever = VectorRetriever()
    retriever.set_bm25_corpus(corpus)

    course_payload = next(r[2] for r in corpus if r[0] == "PY101")
    career_payload = next(r[2] for r in corpus if r[0] == "DS")

    vector_docs = [
        RetrievedDoc(text=career_payload["text"], score=0.95, payload=career_payload),
    ]
    out = retriever._hybrid_rerank(
        "khóa python data science",
        vector_docs,
        top_k=3,
        relevant_ids={"PY101"},
    )
    boosted = next(d for d in out if d.payload.get("course_code") == "PY101")
    plain = retriever._hybrid_rerank(
        "khóa python data science",
        vector_docs,
        top_k=3,
        relevant_ids=None,
    )
    plain_course = next(
        (d for d in plain if d.payload.get("course_code") == "PY101"),
        None,
    )
    assert boosted.score == pytest.approx(plain_course.score + settings.retrieval_graph_boost)


@pytest.mark.parametrize(
    "career_code,career_name,comp_codes",
    [
        ("DS", "Data Scientist", ["L_PY", "L_SQL"]),
        ("GD", "Game Developer", ["L_CS", "L_UNITY"]),
        ("DO", "DevOps Engineer", ["L_DOCKER", "L_K8S"]),
        ("BI", "BI Analyst", ["L_SQL", "L_POWERBI"]),
    ],
)
def test_extract_relevant_ids_from_pathfinding(
    career_code: str,
    career_name: str,
    comp_codes: list[str],
):
    pf = PathfindingResult(
        found=True,
        career_name=career_name,
        career_code=career_code,
        competencies=[
            CompetencyItem(name="Skill A", kind="Tool", code=comp_codes[0]),
            CompetencyItem(name="Skill B", kind="Knowledge", code=comp_codes[1]),
        ],
    )
    ids = extract_relevant_ids_from_graph(pf)
    assert career_code in ids
    assert career_name in ids
    assert comp_codes[0] in ids
    assert comp_codes[1] in ids


def test_extract_relevant_ids_from_course_rec():
    cr = CourseRecResult(
        found=True,
        competency_name="Python",
        courses=[
            CourseItem(course_name="Intro Python", course_code="PY001"),
            CourseItem(course_name="Advanced Python", course_code="PY002"),
        ],
    )
    ids = extract_relevant_ids_from_graph(cr)
    assert "Python" in ids
    assert "PY001" in ids
    assert "PY002" in ids
