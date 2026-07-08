"""
Build / merge D-03 answer_quality_gold.jsonl (32–36 cases).

Usage:
  python scripts/build_answer_quality_gold.py --dry-run
  python scripts/build_answer_quality_gold.py --out data/eval/answer_quality_gold.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUT = PROJECT_ROOT / "data" / "eval" / "answer_quality_gold.jsonl"
GOLD_SOURCE = "quality_gold_v2.1"

# --- Seed: 14 existing cases (3 PF + 3 CR + 3 SG + 5 rel) ---
_SEED: list[dict[str, Any]] = [
    {
        "id": "pf_ds_01",
        "question": "Lộ trình Data Scientist cần học những gì?",
        "intent": "pathfinding",
        "expected_careers": ["Data Scientist"],
        "expected_skills": [
            "Python", "SQL", "Statistics Fundamentals", "Machine Learning Basics",
            "pandas", "scikit-learn", "TensorFlow", "PyTorch",
        ],
        "expected_courses": [],
        "session_setup": {"career": "Data Scientist"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_gd_01",
        "question": "Game Developer cần kỹ năng gì?",
        "intent": "pathfinding",
        "expected_careers": ["Game Developer"],
        "expected_skills": [
            "C#", "C++", "Unity", "Git", "OOP and Design Principles", "SDLC",
        ],
        "expected_courses": [],
        "session_setup": {"career": "Game Developer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_devops_01",
        "question": "DevOps Engineer roadmap",
        "intent": "pathfinding",
        "expected_careers": ["DevOps Engineer"],
        "expected_skills": [
            "Linux", "Docker", "Kubernetes", "Terraform", "AWS", "CI/CD",
            "Networking Basics", "Bash/Shell",
        ],
        "expected_courses": [],
        "session_setup": {"career": "DevOps Engineer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_py_01",
        "question": "Khóa Python nào phù hợp cho người mới?",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Python"],
        "expected_courses": ["CRS_LANG_L_PY_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_react_01",
        "question": "Gợi ý khóa học React beginner",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["React"],
        "expected_courses": ["CRS_FRAM_F_REACT_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_docker_01",
        "question": "Course Docker cho fresher",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Docker"],
        "expected_courses": ["CRS_PLAT_P_DOCKER_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_mle_01",
        "question": "Tôi đã biết Python, muốn làm Machine Learning Engineer còn thiếu gì?",
        "intent": "skills_gap",
        "expected_careers": ["Machine Learning Engineer"],
        "expected_skills": [
            "TensorFlow", "PyTorch", "MLOps Concepts", "Kubernetes",
            "Statistics Fundamentals", "Machine Learning Basics",
        ],
        "expected_courses": [],
        "session_setup": {
            "career": "Machine Learning Engineer",
            "known_by_type": {"CT_LANG": ["Python"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_bi_01",
        "question": "BI Analyst — mình có SQL rồi, cần học thêm skill nào?",
        "intent": "skills_gap",
        "expected_careers": ["BI Analyst"],
        "expected_skills": [
            "Power BI", "Tableau", "Python", "Data Modeling and Analytics",
            "Statistics Fundamentals",
        ],
        "expected_courses": [],
        "session_setup": {
            "career": "BI Analyst",
            "known_by_type": {"CT_LANG": ["SQL"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_bc_01",
        "question": "Blockchain Developer: đã biết JavaScript, gap kỹ năng còn lại?",
        "intent": "skills_gap",
        "expected_careers": ["Blockchain Developer"],
        "expected_skills": [
            "Solidity", "Smart Contract", "Ethereum",
            "Security Fundamentals", "System Design",
        ],
        "expected_courses": [],
        "session_setup": {
            "career": "Blockchain Developer",
            "known_by_type": {"CT_LANG": ["JavaScript"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_react_e2e_01",
        "question": "React cần học gì trước khi bắt đầu?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["JavaScript"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_aws_cert_e2e_01",
        "question": "Chứng chỉ nào liên quan AWS platform?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["AWS Cloud Practitioner", "AWS Solutions Architect"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_cka_e2e_01",
        "question": "CKA validate technology gì?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Kubernetes"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_django_e2e_01",
        "question": "Muốn học Django thì cần biết ngôn ngữ nào?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Python"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_empty_ansible_e2e_01",
        "question": "Ansible có tiên quyết trong hệ thống không?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": [],
        "expected_courses": [],
        "session_setup": {},
        "notes": "expect static empty fallback when coverage=none",
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
]

_EXTRA_PF: list[dict[str, Any]] = [
    {
        "id": "pf_be_02",
        "question": "Làm backend cần học gì?",
        "intent": "pathfinding",
        "expected_careers": ["Backend Developer"],
        "expected_skills": ["Python", "SQL", "Java", "Docker", "AWS", "Git"],
        "expected_courses": [],
        "session_setup": {"career": "Backend Developer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_fe_02",
        "question": "Frontend Developer học gì?",
        "intent": "pathfinding",
        "expected_careers": ["Frontend Developer"],
        "expected_skills": ["JavaScript", "TypeScript", "React", "HTML", "CSS", "Git"],
        "expected_courses": [],
        "session_setup": {"career": "Frontend Developer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_mle_02",
        "question": "Machine Learning Engineer roadmap",
        "intent": "pathfinding",
        "expected_careers": ["Machine Learning Engineer"],
        "expected_skills": ["Python", "TensorFlow", "PyTorch", "MLOps Concepts", "Kubernetes"],
        "expected_courses": [],
        "session_setup": {"career": "Machine Learning Engineer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_cloud_02",
        "question": "Cloud Engineer cần kỹ năng gì?",
        "intent": "pathfinding",
        "expected_careers": ["Cloud Engineer"],
        "expected_skills": ["AWS", "Terraform", "Kubernetes", "Linux", "Docker"],
        "expected_courses": [],
        "session_setup": {"career": "Cloud Engineer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "pf_qa_02",
        "question": "QA Engineer cần học gì?",
        "intent": "pathfinding",
        "expected_careers": ["QA Engineer"],
        "expected_skills": ["SQL", "Python", "Playwright", "pytest", "Testing Strategy"],
        "expected_courses": [],
        "session_setup": {"career": "QA Engineer"},
        "expected_intent": "pathfinding",
        "gold_source": GOLD_SOURCE,
    },
]

_EXTRA_CR: list[dict[str, Any]] = [
    {
        "id": "cr_k8s_02",
        "question": "Khóa Kubernetes cho beginner",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Kubernetes"],
        "expected_courses": ["CRS_PLAT_P_K8S_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_aws_02",
        "question": "Khóa AWS cơ bản",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["AWS"],
        "expected_courses": ["CRS_PLAT_P_AWS_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_django_02",
        "question": "Khóa Django web framework",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Django"],
        "expected_courses": ["CRS_FRAM_F_DJANGO_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_fastapi_02",
        "question": "Học FastAPI cho Python",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["FastAPI"],
        "expected_courses": ["CRS_FRAM_F_FASTAPI_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "cr_angular_02",
        "question": "Khóa học Angular",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Angular"],
        "expected_courses": ["CRS_FRAM_F_ANGULAR_01"],
        "expected_intent": "course_rec",
        "gold_source": GOLD_SOURCE,
    },
]

_EXTRA_SG: list[dict[str, Any]] = [
    {
        "id": "sg_fe_02",
        "question": "Frontend Developer — đã biết HTML/CSS, còn thiếu gì?",
        "intent": "skills_gap",
        "expected_careers": ["Frontend Developer"],
        "expected_skills": ["JavaScript", "React", "TypeScript", "Git"],
        "expected_courses": [],
        "session_setup": {
            "career": "Frontend Developer",
            "known_by_type": {"CT_TOOL": ["HTML", "CSS"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_be_02",
        "question": "Backend Developer đã biết Python, gap còn lại?",
        "intent": "skills_gap",
        "expected_careers": ["Backend Developer"],
        "expected_skills": ["SQL", "Docker", "AWS", "Git", "API Design and Integration"],
        "expected_courses": [],
        "session_setup": {
            "career": "Backend Developer",
            "known_by_type": {"CT_LANG": ["Python"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_ds_02",
        "question": "Data Scientist — có SQL rồi, thiếu skill nào?",
        "intent": "skills_gap",
        "expected_careers": ["Data Scientist"],
        "expected_skills": ["Python", "Statistics Fundamentals", "Machine Learning Basics", "pandas"],
        "expected_courses": [],
        "session_setup": {
            "career": "Data Scientist",
            "known_by_type": {"CT_LANG": ["SQL"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_devops_02",
        "question": "DevOps — biết Linux, cần học thêm gì?",
        "intent": "skills_gap",
        "expected_careers": ["DevOps Engineer"],
        "expected_skills": ["Docker", "Kubernetes", "Terraform", "AWS", "CI/CD"],
        "expected_courses": [],
        "session_setup": {
            "career": "DevOps Engineer",
            "known_by_type": {"CT_PLAT": ["Linux"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "sg_cloud_02",
        "question": "Cloud Engineer đã biết AWS, gap kỹ năng?",
        "intent": "skills_gap",
        "expected_careers": ["Cloud Engineer"],
        "expected_skills": ["Terraform", "Kubernetes", "Linux", "Docker"],
        "expected_courses": [],
        "session_setup": {
            "career": "Cloud Engineer",
            "known_by_type": {"CT_PLAT": ["AWS"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": GOLD_SOURCE,
    },
]

_EXTRA_REL: list[dict[str, Any]] = [
    {
        "id": "rel_spring_02",
        "question": "Spring Framework dựa trên ngôn ngữ gì?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Java"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_vue_02",
        "question": "Vue.js prerequisite là gì?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["JavaScript"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "rel_next_02",
        "question": "Next.js cần học JavaScript hay TypeScript trước?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["JavaScript", "TypeScript"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
]

_HYBRID: list[dict[str, Any]] = [
    {
        "id": "hybrid_ds_py_sql_01",
        "question": "Data Scientist cần học Python hay SQL trước?",
        "intent": "competency_relation",
        "expected_careers": ["Data Scientist"],
        "expected_skills": ["Python", "SQL"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "hybrid_be_java_spring_01",
        "question": "Backend Developer — học Java trước hay Spring trước?",
        "intent": "competency_relation",
        "expected_careers": ["Backend Developer"],
        "expected_skills": ["Java", "Spring Boot"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "hybrid_mle_tf_pt_01",
        "question": "MLE cần TensorFlow hay PyTorch trước khi học MLOps?",
        "intent": "competency_relation",
        "expected_careers": ["Machine Learning Engineer"],
        "expected_skills": ["TensorFlow", "PyTorch", "MLOps Concepts"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": GOLD_SOURCE,
    },
]

_MULTI_TURN: list[dict[str, Any]] = [
    {
        "id": "mt_rel_react_vue_01",
        "question": "React cần học gì trước?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["JavaScript"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "turns": [
            {"question": "React cần học gì trước?"},
            {"question": "Thế còn Vue?"},
        ],
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "mt_rel_aws_azure_01",
        "question": "Chứng chỉ nào validate AWS?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Azure Fundamentals AZ-900"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "turns": [
            {"question": "Chứng chỉ nào validate AWS platform?"},
            {"question": "Thế còn Azure?"},
        ],
        "gold_source": GOLD_SOURCE,
    },
    {
        "id": "mt_rel_django_fastapi_01",
        "question": "Django cần ngôn ngữ nào?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Python"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "turns": [
            {"question": "Muốn học Django thì cần biết ngôn ngữ nào?"},
            {"question": "Thế còn FastAPI?"},
        ],
        "gold_source": GOLD_SOURCE,
    },
]


_EXTRA_V22: list[dict[str, Any]] = [
    {
        "id": "cr_go_v22_01",
        "question": "khóa học Go cho backend",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Go"],
        "expected_courses": ["CRS_LANG_L_GO_01"],
        "expected_intent": "course_rec",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "cr_ts_v22_01",
        "question": "học TypeScript từ đầu",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["TypeScript"],
        "expected_courses": ["CRS_LANG_L_TS_01"],
        "expected_intent": "course_rec",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "cr_flutter_v22_01",
        "question": "khóa học Flutter cho mobile",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Flutter"],
        "expected_courses": ["CRS_FRAM_F_FLUTTER_01"],
        "expected_intent": "course_rec",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "rel_fastapi_lang_v22_01",
        "question": "FastAPI built on language nào?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Python"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "rel_az900_plat_v22_01",
        "question": "AZ-900 liên quan platform nào?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Microsoft Azure"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "rel_oop_java_v22_01",
        "question": "OOP hỗ trợ ngôn ngữ Java thế nào?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["Java"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "pf_sec_v22_01",
        "question": "Security Engineer học gì?",
        "intent": "pathfinding",
        "expected_careers": ["Security Engineer"],
        "expected_skills": ["Python", "Linux", "AWS", "Networking Basics", "Security Fundamentals"],
        "expected_courses": [],
        "session_setup": {"career": "Security Engineer"},
        "expected_intent": "pathfinding",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "pf_mob_v22_01",
        "question": "Mobile Developer roadmap",
        "intent": "pathfinding",
        "expected_careers": ["Mobile Developer"],
        "expected_skills": ["Kotlin", "Swift", "Flutter", "Git", "REST API Design"],
        "expected_courses": [],
        "session_setup": {"career": "Mobile Developer"},
        "expected_intent": "pathfinding",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "sg_da_v22_01",
        "question": "Data Analyst — đã biết Excel, còn thiếu gì?",
        "intent": "skills_gap",
        "expected_careers": ["Data Analyst"],
        "expected_skills": ["SQL", "Python", "Power BI", "Statistics Fundamentals"],
        "expected_courses": [],
        "session_setup": {
            "career": "Data Analyst",
            "known_by_type": {"CT_TOOL": ["Excel"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "sg_qa_v22_01",
        "question": "QA Engineer biết SQL rồi, gap skill?",
        "intent": "skills_gap",
        "expected_careers": ["QA Engineer"],
        "expected_skills": ["Python", "Playwright", "pytest", "Testing Strategy"],
        "expected_courses": [],
        "session_setup": {
            "career": "QA Engineer",
            "known_by_type": {"CT_LANG": ["SQL"]},
        },
        "expected_intent": "skills_gap",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "hybrid_fe_react_vue_v22_01",
        "question": "Frontend Developer nên học React hay Vue trước?",
        "intent": "competency_relation",
        "expected_careers": ["Frontend Developer"],
        "expected_skills": ["React", "Vue"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "hybrid_de_spark_kafka_v22_01",
        "question": "Data Engineer học Spark hay Kafka trước?",
        "intent": "competency_relation",
        "expected_careers": ["Data Engineer"],
        "expected_skills": ["Apache Spark", "Apache Kafka"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "mt_rel_angular_vue_v22_01",
        "question": "Angular cần học gì trước?",
        "intent": "competency_relation",
        "expected_careers": [],
        "expected_skills": ["TypeScript"],
        "expected_courses": [],
        "session_setup": {},
        "expected_intent": "competency_relation",
        "turns": [
            {"question": "Angular cần học gì trước?"},
            {"question": "Thế còn Vue?"},
        ],
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
    {
        "id": "mt_pivot_vue_course_v22_01",
        "question": "Oke cho mình khóa Vue",
        "intent": "course_rec",
        "expected_careers": [],
        "expected_skills": ["Vue"],
        "expected_courses": ["CRS_FRAM_F_VUE_01"],
        "session_setup": {},
        "expected_intent": "course_rec",
        "turns": [
            {"question": "Vue.js prerequisite là gì?"},
            {"question": "Thế còn React?"},
            {"question": "Oke cho mình khóa Vue"},
        ],
        "gold_source": "quality_gold_v2.2",
        "gold_cohort": "v22_new14",
    },
]


def _tag_legacy_cohort(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in cases:
        tagged = dict(row)
        if not tagged.get("gold_cohort"):
            tagged["gold_cohort"] = "v21_legacy"
        out.append(tagged)
    return out


def _neo4j_query(client: Any, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    with client.session() as session:
        return list(session.run(cypher, params))


def _probe_neo4j_case(case: dict[str, Any], graph: Any) -> tuple[str, str]:
    """Return (neo4j_probe_status, neo4j_probe_notes)."""
    notes: list[str] = []
    status = "ok"

    for career in case.get("expected_careers") or []:
        hits = graph.search_careers(str(career), limit=3)
        names = [
            str(c.get("name") or c.get("career_name") or "")
            for c in (hits.get("careers") or [])
            if isinstance(c, dict)
        ]
        if career not in names and not any(career.lower() in n.lower() for n in names if n):
            notes.append(f"career '{career}' weak match")
            status = "warn"

    for code in case.get("expected_courses") or []:
        rows = _neo4j_query(
            graph._client,
            "MATCH (c:Course {course_code: $code}) RETURN c.course_code AS code LIMIT 1",
            {"code": str(code)},
        )
        if not rows:
            notes.append(f"course '{code}' not in graph")
            status = "fail"

    intent = str(case.get("intent") or "")
    if intent == "competency_relation" and case.get("expected_skills"):
        for skill in case.get("expected_skills") or []:
            rows = _neo4j_query(
                graph._client,
                "MATCH (n) WHERE n.competency_name = $name OR n.skill_name = $name "
                "RETURN n LIMIT 1",
                {"name": str(skill)},
            )
            if not rows:
                notes.append(f"skill '{skill}' not found")
                if status != "fail":
                    status = "warn"

    if not notes:
        notes.append("ok")
    return status, "; ".join(notes)


def build_cases() -> list[dict[str, Any]]:
    cases = (
        _SEED
        + _EXTRA_PF
        + _EXTRA_CR
        + _EXTRA_SG
        + _EXTRA_REL
        + _HYBRID
        + _MULTI_TURN
        + _EXTRA_V22
    )
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in cases:
        cid = row["id"]
        if cid in seen:
            continue
        seen.add(cid)
        out.append(row)
    return _tag_legacy_cohort(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build answer_quality_gold.jsonl")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--probe-neo4j",
        action="store_true",
        help="Probe Neo4j for expected careers/courses/skills; fail on mismatch",
    )
    args = parser.parse_args()

    cases = build_cases()
    print(f"Built {len(cases)} cases")
    for row in cases:
        q = str(row.get("question") or "")[:50].encode("ascii", "replace").decode("ascii")
        print(f"  {row['id']:30} {row['intent']:22} {q}")

    if args.probe_neo4j and not args.dry_run:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=True)
        from app.graph.repository import GraphRepository

        graph = GraphRepository()
        failed = 0
        try:
            for row in cases:
                status, notes = _probe_neo4j_case(row, graph)
                row["neo4j_probe_status"] = status
                row["neo4j_probe_notes"] = notes
                if status == "fail":
                    failed += 1
                    print(f"  FAIL probe {row['id']}: {notes}")
                elif status == "warn":
                    print(f"  WARN probe {row['id']}: {notes}")
        finally:
            graph.close()
        if failed:
            print(f"ERROR: {failed} case(s) failed Neo4j probe")
            raise SystemExit(1)

    if args.dry_run:
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in cases:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
