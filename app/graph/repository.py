from __future__ import annotations

from difflib import SequenceMatcher
from typing import Sequence

from app.core.config import settings
from app.graph.models import (
    CareerSkillCoursesResult,
    CompetencyItem,
    CompetencyRelationResult,
    CourseRecResult,
    PathfindingResult,
)
from app.graph.neo4j_client import Neo4jClient
from app.graph.queries.career_multihop import fetch_courses_for_career_skills
from app.graph.queries.competency_relation import (
    batch_fetch_prerequisites,
    fetch_competency_relations,
)
from app.graph.queries.course_rec import (
    fetch_course_recommendations,
    fetch_courses_by_type,
)
from app.graph.queries.pathfinding import fetch_pathfinding, fetch_pathfinding_by_type
from app.graph.queries.subject_career import fetch_subject_to_careers
from app.graph.skills_gap import apply_skills_gap_to_result, order_skills_by_prerequisites
from app.rag.aliases import subject_search_terms


class GraphRepository:
    """Lớp Neo4j Query — Bước 2 (pathfinding + course_rec).

    Các seed_* tham số là output của tight fusion (A-01): danh sách code lấy từ
    Qdrant vector hits, dùng để dẫn hướng Cypher (boost match, không lọc cứng).
    """

    def __init__(self, client: Neo4jClient | None = None) -> None:
        self._client = client or Neo4jClient()

    def pathfinding(
        self,
        career: str,
        *,
        known_skills: list[str] | None = None,
        seed_career_codes: Sequence[str] | None = None,
        seed_competency_codes: Sequence[str] | None = None,
    ) -> PathfindingResult:
        result = fetch_pathfinding(
            self._client,
            career,
            seed_career_codes=seed_career_codes,
            seed_competency_codes=seed_competency_codes,
        )
        if known_skills:
            apply_skills_gap_to_result(result, known_skills)
        else:
            result.skills_known = []
            result.skills_missing = list(result.competencies)
        if settings.competency_relation_enrich:
            self._enrich_pathfinding_result(result, known_skills=known_skills)
        return result

    def pathfinding_by_type(
        self,
        career: str,
        rel_type: str,
        *,
        known_skills: list[str] | None = None,
        seed_career_codes: Sequence[str] | None = None,
        seed_competency_codes: Sequence[str] | None = None,
    ) -> PathfindingResult:
        result = fetch_pathfinding_by_type(
            self._client,
            career,
            rel_type,
            seed_career_codes=seed_career_codes,
            seed_competency_codes=seed_competency_codes,
        )
        if known_skills:
            apply_skills_gap_to_result(result, known_skills)
        else:
            result.skills_known = []
            result.skills_missing = list(result.competencies)
        if settings.competency_relation_enrich:
            self._enrich_pathfinding_result(result, known_skills=known_skills)
        return result

    def _enrich_pathfinding_result(
        self,
        result: PathfindingResult,
        *,
        known_skills: list[str] | None = None,
    ) -> None:
        from app.graph.skills_gap import resolve_known_item_codes

        targets = list(result.skills_missing or result.competencies)
        codes = [c.code for c in targets if c.code]
        if not codes:
            return
        prereq_map = batch_fetch_prerequisites(self._client, codes)
        known_codes = resolve_known_item_codes(known_skills, competency_catalog=targets)
        ordered = order_skills_by_prerequisites(targets, prereq_map, known_codes)
        if result.skills_missing:
            result.skills_missing = ordered
        for comp in ordered:
            comp.prerequisite_codes = [
                p["code"]
                for p in prereq_map.get(comp.code or "", [])
                if p.get("code")
            ]

    def competency_relations(
        self,
        competency: str,
        *,
        anchor_code: str | None = None,
        question_kind: str | None = None,
    ) -> CompetencyRelationResult:
        return fetch_competency_relations(
            self._client,
            competency,
            anchor_code=anchor_code,
            question_kind=question_kind,
        )

    def course_recommendation(
        self,
        competency: str,
        *,
        seed_course_codes: Sequence[str] | None = None,
    ) -> CourseRecResult:
        return fetch_course_recommendations(
            self._client, competency, seed_course_codes=seed_course_codes
        )

    def course_recommendation_by_type(
        self,
        competency: str,
        rel_type: str,
        *,
        seed_course_codes: Sequence[str] | None = None,
    ) -> CourseRecResult:
        return fetch_courses_by_type(
            self._client,
            competency,
            rel_type,
            seed_course_codes=seed_course_codes,
        )

    def courses_for_career_skills(
        self,
        career: str,
        skill_names: list[str],
        *,
        rel_type: str | None = None,
        max_per_skill: int = 4,
        seed_career_codes: Sequence[str] | None = None,
        seed_course_codes: Sequence[str] | None = None,
    ) -> CareerSkillCoursesResult:
        """A-02: Career → Competency → Course trong một Cypher (thay vòng lặp N query)."""
        return fetch_courses_for_career_skills(
            self._client,
            career,
            skill_names,
            rel_type=rel_type,
            max_per_skill=max_per_skill,
            seed_career_codes=seed_career_codes,
            seed_course_codes=seed_course_codes,
        )

    def subject_to_careers(
        self,
        subject_name: str,
        *,
        limit: int = 15,
    ) -> list[dict]:
        """
        C-03: Subject/Program → Course → Competency → Career (multi-hop).

        ``subject_name`` có thể là alias (OOP, CSDL) hoặc tên đầy đủ; tự resolve
        qua ``subject_search_terms``.
        """
        terms = subject_search_terms(subject_name)
        if not terms:
            return []
        codes: list[str] = []
        if subject_name and subject_name.strip().isupper() and len(subject_name.strip()) <= 8:
            codes.append(subject_name.strip())
        return fetch_subject_to_careers(
            self._client,
            search_terms=terms,
            subject_codes=codes,
            limit=limit,
        )

    def search_careers(self, query: str, *, limit: int = 6) -> dict[str, object]:
        name = (query or "").strip()
        if not name:
            return {"exact": False, "suggestions": []}
        if not self._client.available:
            return {"exact": False, "suggestions": []}

        cypher = """
MATCH (c:Career)
WITH DISTINCT trim(c.career_name) AS career_name
WHERE career_name IS NOT NULL AND career_name <> ''
RETURN career_name
ORDER BY career_name
"""
        try:
            with self._client.session() as session:
                rows = session.run(cypher).data()
        except Exception:
            return {"exact": False, "suggestions": []}

        names = [str(r.get("career_name") or "").strip() for r in rows]
        names = [n for n in names if n]
        q = name.lower()
        exact = any(n.lower() == q for n in names)
        if exact:
            return {"exact": True, "suggestions": []}

        scored: list[tuple[float, str]] = []
        for n in names:
            nl = n.lower()
            score = SequenceMatcher(None, q, nl).ratio()
            if q in nl:
                score += 0.35
            scored.append((score, n))
        scored.sort(key=lambda x: (-x[0], x[1]))
        suggestions = [n for s, n in scored if s >= 0.25][: max(1, min(limit, 12))]
        return {"exact": False, "suggestions": suggestions}

    def close(self) -> None:
        self._client.close()
