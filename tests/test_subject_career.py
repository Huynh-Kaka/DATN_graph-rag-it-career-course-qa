"""C-03 — Subject → Course → Competency → Career multi-hop."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.graph.queries.subject_career import fetch_subject_to_careers
from app.graph.repository import GraphRepository
from app.graph.subject_career_case_study import (
    OOP_CASE_STUDY_DOC,
    format_subject_career_chain,
    format_subject_career_reply,
)
from app.intent.router import IntentRouterService
from app.rag.aliases import (
    looks_like_subject_career_question,
    resolve_subject_alias,
    subject_search_terms,
)


# Dữ liệu mock đa dạng nghề — không chỉ Backend.
_MOCK_GRAPH_ROWS = [
    {
        "subject": "Lập trình hướng đối tượng",
        "subject_code": "SUB_OOP",
        "course": "Python OOP Fundamentals",
        "course_code": "CRS_PY_OOP",
        "competency": "Python",
        "competency_code": "L_PY",
        "career": "Data Scientist",
        "career_code": "CAR_DS",
    },
    {
        "subject": "Lập trình hướng đối tượng",
        "subject_code": "SUB_OOP",
        "course": "Java Object-Oriented Programming",
        "course_code": "CRS_JAVA_OOP",
        "competency": "Java",
        "competency_code": "L_JAVA",
        "career": "Backend Developer",
        "career_code": "CAR_BE",
    },
    {
        "subject": "Lập trình hướng đối tượng",
        "subject_code": "SUB_OOP",
        "course": "C# OOP Basics",
        "course_code": "CRS_CS_OOP",
        "competency": "C#",
        "competency_code": "L_CS",
        "career": "Game Developer",
        "career_code": "CAR_GD",
    },
    {
        "subject": "Cơ sở dữ liệu",
        "subject_code": "SUB_DB",
        "course": "SQL for Analysts",
        "course_code": "CRS_SQL_01",
        "competency": "SQL",
        "competency_code": "K_SQL",
        "career": "Data Analyst",
        "career_code": "CAR_DA",
    },
    {
        "subject": "Cơ sở dữ liệu",
        "subject_code": "SUB_DB",
        "course": "PostgreSQL Essentials",
        "course_code": "CRS_PG_01",
        "competency": "PostgreSQL",
        "competency_code": "P_PG",
        "career": "BI Analyst",
        "career_code": "CAR_BI",
    },
    {
        "subject": "Trí tuệ nhân tạo",
        "subject_code": "SUB_AI",
        "course": "Intro to Machine Learning",
        "course_code": "CRS_ML_01",
        "competency": "Machine Learning Basics",
        "competency_code": "K_ML",
        "career": "Machine Learning Engineer",
        "career_code": "CAR_MLE",
    },
    {
        "subject": "Mạng máy tính",
        "subject_code": "SUB_NET",
        "course": "Linux Networking Lab",
        "course_code": "CRS_NET_01",
        "competency": "Networking Basics",
        "competency_code": "K_NET",
        "career": "DevOps Engineer",
        "career_code": "CAR_DEVOPS",
    },
    {
        "subject": "Phát triển ứng dụng web",
        "subject_code": "SUB_WEB",
        "course": "React for Beginners",
        "course_code": "CRS_REACT_01",
        "competency": "React",
        "competency_code": "F_REACT",
        "career": "Frontend Developer",
        "career_code": "CAR_FE",
    },
    {
        "subject": "Học máy",
        "subject_code": "SUB_ML",
        "course": "scikit-learn Workshop",
        "course_code": "CRS_SKL_01",
        "competency": "scikit-learn",
        "competency_code": "T_SKL",
        "career": "Data Scientist",
        "career_code": "CAR_DS",
    },
    {
        "subject": "Học máy",
        "subject_code": "SUB_ML",
        "course": "TensorFlow Basics",
        "course_code": "CRS_TF_01",
        "competency": "TensorFlow",
        "competency_code": "F_TF",
        "career": "Machine Learning Engineer",
        "career_code": "CAR_MLE",
    },
]


def _mock_neo4j_client(rows: list[dict]):
    client = MagicMock()
    client.available = True
    session = MagicMock()
    session.run.return_value.data.return_value = rows
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    client.session.return_value = session
    return client


def test_subject_search_terms_oop():
    terms = subject_search_terms("OOP")
    assert "lập trình hướng đối tượng" in [t.lower() for t in terms] or "OOP" in terms


def test_resolve_subject_alias_oop():
    assert resolve_subject_alias("học OOP cơ bản") == "Lap trinh huong doi tuong"


def test_looks_like_subject_career_question():
    assert looks_like_subject_career_question(
        "Học môn OOP thì sau này làm được những nghề nào?"
    )
    assert not looks_like_subject_career_question("Thời tiết Hà Nội hôm nay")


def test_router_detects_subject_career_intent():
    router = IntentRouterService(registry=MagicMock())
    outcome = router._try_subject_career_route(
        "Học môn OOP thì sau này làm được những nghề nào?"
    )
    assert outcome is not None
    assert outcome.route.intent == "subject_career"
    assert outcome.route.entities.subject == "Lap trinh huong doi tuong"
    assert outcome.stop is False


def test_fetch_subject_to_careers_dedup():
    client = _mock_neo4j_client(_MOCK_GRAPH_ROWS)
    rows = fetch_subject_to_careers(
        client, search_terms=["OOP", "lập trình hướng đối tượng"], limit=20
    )
    careers = {r["career"] for r in rows}
    assert "Data Scientist" in careers
    assert "Backend Developer" in careers
    assert "Game Developer" in careers
    assert "Data Analyst" in careers
    assert "DevOps Engineer" in careers
    assert "Frontend Developer" in careers
    assert "Machine Learning Engineer" in careers
    assert len(careers) >= 7


def test_format_subject_career_chain_oop():
    row = _MOCK_GRAPH_ROWS[0]
    chain = format_subject_career_chain(row)
    assert "Học môn Lập trình hướng đối tượng" in chain
    assert "khóa Python OOP Fundamentals" in chain
    assert "nắm Python" in chain
    assert "nghề Data Scientist" in chain
    assert "->" not in chain
    assert "BUILT_ON" not in chain


def test_format_reply_lists_diverse_careers(capsys):
    oop_rows = [r for r in _MOCK_GRAPH_ROWS if r["subject_code"] == "SUB_OOP"]
    reply = format_subject_career_reply(
        oop_rows, subject_label="Lập trình hướng đối tượng"
    )
    assert "Data Scientist" in reply
    assert "Backend Developer" in reply
    assert "Game Developer" in reply
    assert "lộ trình" in reply.lower()
    assert "multi-hop" not in reply.lower()
    assert "BUILT_ON" not in reply


def test_repository_subject_to_careers(monkeypatch):
    client = _mock_neo4j_client(_MOCK_GRAPH_ROWS)
    repo = GraphRepository(client=client)
    rows = repo.subject_to_careers("OOP")
    assert len(rows) >= 3
    careers = {r["career"] for r in rows}
    assert "Game Developer" in careers
    assert "Data Scientist" in careers


def test_oop_keyword_prints_diverse_chains(capsys):
    """In chuỗi mẫu từ khóa OOP — đa nghề, không chỉ Backend."""
    client = _mock_neo4j_client(_MOCK_GRAPH_ROWS)
    rows = fetch_subject_to_careers(client, search_terms=["OOP"], limit=15)
    oop_rows = [r for r in rows if r["career"] in (
        "Backend Developer",
        "Data Scientist",
        "Game Developer",
    )]
    assert len(oop_rows) >= 3
    lines = [format_subject_career_chain(r) for r in oop_rows]
    print("\n".join(lines))
    captured = capsys.readouterr()
    assert "Backend Developer" in captured.out
    assert "Data Scientist" in captured.out
    assert "Game Developer" in captured.out
    assert "Môn học [" not in captured.out
    assert "Học môn" in captured.out


def test_case_study_doc_present():
    assert "OOP" in OOP_CASE_STUDY_DOC
    assert "Backend Developer" in OOP_CASE_STUDY_DOC
    assert "Data Scientist" in OOP_CASE_STUDY_DOC
