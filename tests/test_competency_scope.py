from app.intent.competency_scope import detect_competency_type_scope


def test_soft_skill_scope_vi():
    assert (
        detect_competency_type_scope("tôi muốn biết những kỹ năng mềm của vị trí BA")
        == "CT_SOFT"
    )


def test_soft_skill_scope_from_entity():
    assert (
        detect_competency_type_scope(
            "BA cần gì",
            competency_entity="kỹ năng mềm",
        )
        == "CT_SOFT"
    )


def test_soft_skill_scope_en():
    assert detect_competency_type_scope("softskill của DevOps") == "CT_SOFT"


def test_no_scope_general_pathfinding():
    assert detect_competency_type_scope("Backend cần học gì") is None


def test_cert_scope():
    assert detect_competency_type_scope("chứng chỉ cần cho Data Analyst") == "CT_CERT"
