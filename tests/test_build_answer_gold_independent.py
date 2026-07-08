"""D-10 — independent gold built from Excel without GraphRepository."""

from scripts.build_answer_gold_independent import (
    build_career_name_index,
    build_item_name_index,
    course_rec_gold_from_excel,
    pathfinding_gold_from_excel,
)


def test_pathfinding_gold_from_excel_rows():
    career_rows = [
        {"career_code": "GD", "career_name": "Game Developer"},
    ]
    career_map = [
        {"career_code": "GD", "item_code": "L_CSHARP", "type_code": "CT_LANG", "priority_group": 1},
        {"career_code": "GD", "item_code": "F_UNITY", "type_code": "CT_FRAM", "priority_group": 2},
    ]
    item_names = {"L_CSHARP": "C#", "F_UNITY": "Unity"}
    skills = pathfinding_gold_from_excel(
        "Game Developer",
        career_rows=career_rows,
        career_map_rows=career_map,
        item_names=item_names,
    )
    assert skills == ["C#", "Unity"]


def test_course_rec_gold_from_excel_rows():
    course_map = [
        {
            "item_code": "L_PY",
            "course_code": "CRS_LANG_L_PY_01",
            "relation_type": "TEACH",
            "coverage_level": 3,
        },
        {
            "item_code": "L_PY",
            "course_code": "CRS_LANG_L_PY_02",
            "relation_type": "TEACH",
            "coverage_level": 1,
        },
    ]
    item_names = {"L_PY": "Python"}
    codes = course_rec_gold_from_excel(
        "Python",
        course_map_rows=course_map,
        item_names=item_names,
    )
    assert codes == ["CRS_LANG_L_PY_01", "CRS_LANG_L_PY_02"]


def test_build_item_name_index():
    sheet_cache = {
        "programming_language": [{"item_code": "L_GO", "item_name": "Go"}],
        "framework": [],
        "platform": [],
        "tool": [],
        "knowledge": [],
        "softskill": [],
        "certification": [],
    }
    index = build_item_name_index(sheet_cache)
    assert index["L_GO"] == "Go"


def test_build_career_name_index():
    rows = [{"career_code": "BE", "career_name": "Backend Developer"}]
    assert build_career_name_index(rows)["BE"] == "Backend Developer"
