from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CompetencyTypeCode(str, Enum):
    LANG = "CT_LANG"
    FRAM = "CT_FRAM"
    PLAT = "CT_PLAT"
    TOOL = "CT_TOOL"
    KNOW = "CT_KNOW"
    SOFT = "CT_SOFT"
    CERT = "CT_CERT"


class CompetencyItem(BaseModel):
    name: str
    kind: str
    priority: int | None = None
    code: str | None = None
    # True khi competency thuộc nhóm "seed" từ vector retrieval (A-01 tight fusion).
    is_seed: bool = False
    prerequisite_codes: list[str] = Field(default_factory=list)
    advisory_prerequisites: list[str] = Field(default_factory=list)
    related_codes: list[str] = Field(default_factory=list)


class PathfindingResult(BaseModel):
    found: bool = False
    career_name: str | None = None
    career_code: str | None = None
    industry: str | None = None
    competencies: list[CompetencyItem] = Field(default_factory=list)
    skills_known: list[CompetencyItem] = Field(default_factory=list)
    skills_missing: list[CompetencyItem] = Field(default_factory=list)
    error: str | None = None


class CourseItem(BaseModel):
    course_name: str
    course_code: str | None = None
    organization: str | None = None
    level: str | None = None
    subtitle: str | None = None
    url: str | None = None
    duration_hours: float | int | str | None = None
    # TEACH_*.coverage_level — mức bao phủ kiến thức (C-01, cao hơn = ưu tiên hơn).
    coverage_level: int | None = None
    # True khi course thuộc nhóm "seed" từ vector retrieval (A-01 tight fusion).
    is_seed: bool = False


class CourseRecResult(BaseModel):
    found: bool = False
    competency_name: str | None = None
    competency_kind: str | None = None
    competency_code: str | None = None
    courses: list[CourseItem] = Field(default_factory=list)
    error: str | None = None
    via_prerequisites: list[dict] = Field(default_factory=list)
    fallback_reason: str | None = None


class SkillCoursesBlock(BaseModel):
    """Một competency và các khóa học TEACH_* (A-02 multi-hop)."""

    competency_name: str
    competency_kind: str | None = None
    competency_code: str | None = None
    priority: int | None = None
    courses: list[CourseItem] = Field(default_factory=list)


class CareerSkillCoursesResult(BaseModel):
    """Kết quả gộp Career → Competency → Course trong một lần truy vấn."""

    found: bool = False
    career_name: str | None = None
    career_code: str | None = None
    blocks: list[SkillCoursesBlock] = Field(default_factory=list)
    error: str | None = None


class CompetencyRelationEdge(BaseModel):
    relation_id: str | None = None
    rel_type: str
    from_code: str
    from_name: str
    from_type_code: CompetencyTypeCode | None = None
    to_code: str
    to_name: str
    to_type_code: CompetencyTypeCode | None = None
    note: str | None = None


CoverageLevel = Literal["full", "partial", "none"]


class CompetencyRelationResult(BaseModel):
    found: bool = False
    anchor_name: str | None = None
    anchor_code: str | None = None
    anchor_type_code: CompetencyTypeCode | None = None
    outgoing: list[CompetencyRelationEdge] = Field(default_factory=list)
    incoming: list[CompetencyRelationEdge] = Field(default_factory=list)
    error: str | None = None
    coverage: CoverageLevel = "none"
    resolve_candidates: list[dict] = Field(default_factory=list)
