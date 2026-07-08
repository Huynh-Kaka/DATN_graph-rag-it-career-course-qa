from app.rag.fusion import FusionService
from app.rag.retriever import RetrievedDoc


def test_fusion_evidence():
    fusion = FusionService()
    out = fusion.aggregate(
        graph_payload={
            "found": True,
            "career_code": "BE",
            "career_name": "Backend Developer",
            "courses": [{"course_code": "PY101"}],
        },
        vector_docs=[
            RetrievedDoc(text="snippet", score=0.9, payload={"chunk_id": "c1"}),
        ],
    )
    assert "Backend Developer" in out["context_block"]
    assert "PY101" in out["evidence"]["course_codes"]
    assert "c1" in out["evidence"]["chunk_ids"]
