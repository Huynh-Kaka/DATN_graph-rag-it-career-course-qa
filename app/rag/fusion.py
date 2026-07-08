from __future__ import annotations

from typing import Any, Iterable

from app.rag.retriever import RetrievedDoc


# Tight fusion (A-01): map vector hits → graph seed node identifiers.
# Mỗi vector hit trong Qdrant có payload theo schema của scripts/index_qdrant.py:
#   { "doc_type": "career"|"competency"|"course",
#     "canonical_id": <code>, "career_code"|"item_code"|"course_code": ... }
# Hàm này gom & chuẩn hóa thành 3 nhóm code để bơm vào Cypher ($seed_*_codes).
def extract_relevant_ids_from_graph(
    graph_payload: dict[str, Any] | Any | None,
) -> set[str]:
    """
    A-03: Gom ID Career / Competency / Course từ kết quả Neo4j
    để graph-aware re-ranking vector docs.
    """
    if graph_payload is None:
        return set()
    if hasattr(graph_payload, "model_dump"):
        graph = graph_payload.model_dump()
    elif isinstance(graph_payload, dict):
        graph = graph_payload
    else:
        return set()

    ids: set[str] = set()

    def _add(value: Any) -> None:
        if value is None:
            return
        token = str(value).strip()
        if token:
            ids.add(token)

    _add(graph.get("career_code"))
    _add(graph.get("career_name"))
    _add(graph.get("competency_name"))

    for key in ("competencies", "skills_known", "skills_missing"):
        for item in graph.get(key) or []:
            if isinstance(item, dict):
                _add(item.get("code"))
                _add(item.get("item_code"))

    for block in graph.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        _add(block.get("competency_code"))
        _add(block.get("competency_name"))
        for course in block.get("courses") or []:
            if isinstance(course, dict):
                _add(course.get("course_code"))

    for course in graph.get("courses") or []:
        if isinstance(course, dict):
            _add(course.get("course_code"))

    return ids


def map_hits_to_graph_nodes(
    hits: Iterable[RetrievedDoc] | Iterable[str] | None,
) -> dict[str, list[str]]:
    career_codes: list[str] = []
    competency_codes: list[str] = []
    course_codes: list[str] = []

    if not hits:
        return {
            "career_codes": [],
            "competency_codes": [],
            "course_codes": [],
        }

    def _push(bucket: list[str], value: Any) -> None:
        if value is None:
            return
        code = str(value).strip()
        if not code or code in bucket:
            return
        bucket.append(code)

    for hit in hits:
        if not isinstance(hit, RetrievedDoc):
            continue
        payload = hit.payload or {}
        doc_type = str(payload.get("doc_type") or "").lower()
        canonical = payload.get("canonical_id")

        if doc_type == "career":
            _push(career_codes, payload.get("career_code") or canonical)
        elif doc_type == "competency":
            _push(competency_codes, payload.get("item_code") or canonical)
        elif doc_type == "course":
            _push(course_codes, payload.get("course_code") or canonical)
            # Tận dụng list competency mà course này dạy (nếu corpus có)
            for comp in payload.get("competencies") or []:
                if isinstance(comp, dict):
                    _push(competency_codes, comp.get("item_code"))
                elif isinstance(comp, str):
                    _push(competency_codes, comp)
        else:
            # Best-effort: payload có thể đến từ corpus chưa chuẩn hóa.
            if payload.get("career_code"):
                _push(career_codes, payload.get("career_code"))
            if payload.get("item_code"):
                _push(competency_codes, payload.get("item_code"))
            if payload.get("course_code"):
                _push(course_codes, payload.get("course_code"))

    return {
        "career_codes": career_codes,
        "competency_codes": competency_codes,
        "course_codes": course_codes,
    }


class FusionService:
    """Tight fusion: graph ground truth (định hướng bởi vector hits) + snippets + LLM draft."""

    def aggregate(
        self,
        *,
        graph_payload: dict[str, Any] | None,
        vector_docs: list[RetrievedDoc] | list[str],
        llm_draft: str | None = None,
        graph_seed_ids: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        graph = graph_payload or {}
        docs: list[RetrievedDoc] = []
        for item in vector_docs:
            if isinstance(item, RetrievedDoc):
                docs.append(item)
            elif isinstance(item, str) and item.strip():
                docs.append(RetrievedDoc(text=item.strip(), score=0.0, payload={}))

        seed_ids = graph_seed_ids or map_hits_to_graph_nodes(docs)
        evidence = self.build_evidence(
            graph_payload=graph,
            vector_docs=docs,
            graph_seed_ids=seed_ids,
        )
        context_lines: list[str] = []

        if graph.get("found"):
            if graph.get("career_name"):
                context_lines.append(f"Nghề (Neo4j): {graph['career_name']}")
            if graph.get("competency_name"):
                context_lines.append(f"Kỹ năng (Neo4j): {graph['competency_name']}")
            comps = graph.get("competencies") or graph.get("skills_missing") or []
            if comps:
                names = [
                    c.get("name") if isinstance(c, dict) else str(c)
                    for c in comps[:12]
                ]
                context_lines.append("Kỹ năng từ đồ thị: " + ", ".join(names))
            courses = graph.get("courses") or []
            if courses:
                context_lines.append(f"Có {len(courses)} khóa học từ Neo4j.")

        prereq_chunks: list[str] = []
        for comp in graph.get("skills_missing") or graph.get("competencies") or []:
            if not isinstance(comp, dict):
                continue
            name = comp.get("name") or comp.get("item_name")
            adv = comp.get("advisory_prerequisites") or []
            pcodes = comp.get("prerequisite_codes") or []
            if adv:
                prereq_chunks.append(f"{name}: {'; '.join(str(a) for a in adv[:3])}")
            elif pcodes and name:
                prereq_chunks.append(f"{name} ← {', '.join(str(c) for c in pcodes[:4])}")
        if prereq_chunks:
            context_lines.append(
                "Tiên quyết (competency_relation): " + " | ".join(prereq_chunks[:6])
            )

        if graph.get("outgoing") or graph.get("incoming"):
            rel_names: list[str] = []
            for bucket in ("outgoing", "incoming"):
                for edge in graph.get(bucket) or []:
                    if not isinstance(edge, dict):
                        continue
                    rel = edge.get("rel_type") or "REL"
                    target = edge.get("to_name") or edge.get("from_name") or edge.get("to_code")
                    if target:
                        rel_names.append(f"{rel}→{target}")
            if rel_names:
                context_lines.append("Quan hệ graph: " + ", ".join(rel_names[:8]))

        # Lộ "seed nodes" để LLM/debugging biết tight fusion đang dẫn hướng cái gì.
        seed_chunks: list[str] = []
        for label, key in (
            ("career", "career_codes"),
            ("competency", "competency_codes"),
            ("course", "course_codes"),
        ):
            codes = seed_ids.get(key) or []
            if codes:
                seed_chunks.append(f"{label}={','.join(codes[:6])}")
        if seed_chunks:
            context_lines.append("Seed nodes (vector→graph): " + "; ".join(seed_chunks))

        for i, doc in enumerate(docs[:3], start=1):
            context_lines.append(f"[Vector {i}] {doc.text[:400]}")

        return {
            "context_block": "\n".join(context_lines),
            "llm_draft": llm_draft,
            "evidence": evidence,
            "graph_seed_ids": seed_ids,
        }

    @staticmethod
    def build_evidence(
        *,
        graph_payload: dict[str, Any] | None,
        vector_docs: list[RetrievedDoc],
        graph_seed_ids: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        graph = graph_payload or {}
        career_ids: list[str] = []
        if graph.get("career_code"):
            career_ids.append(str(graph["career_code"]))
        elif graph.get("career_name"):
            career_ids.append(str(graph["career_name"]))

        course_codes: list[str] = []
        for c in graph.get("courses") or []:
            if isinstance(c, dict) and c.get("course_code"):
                course_codes.append(str(c["course_code"]))

        chunk_ids: list[str] = []
        for doc in vector_docs:
            cid = doc.payload.get("chunk_id") or doc.payload.get("doc_id")
            if cid:
                chunk_ids.append(str(cid))

        evidence = {
            "career_ids": career_ids,
            "course_codes": course_codes,
            "chunk_ids": chunk_ids,
        }
        if graph_seed_ids:
            evidence["graph_seed_ids"] = {
                k: list(v) for k, v in graph_seed_ids.items() if v
            }
        return evidence
