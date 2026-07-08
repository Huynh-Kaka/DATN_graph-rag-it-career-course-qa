"""Build script produces 52 v2.2 gold cases with cohort tags."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_answer_quality_gold import build_cases  # noqa: E402


def test_build_cases_count():
    cases = build_cases()
    assert len(cases) == 52


def test_no_duplicate_ids():
    cases = build_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_cohort_tags():
    cases = build_cases()
    legacy = [c for c in cases if c.get("gold_cohort") == "v21_legacy"]
    new14 = [c for c in cases if c.get("gold_cohort") == "v22_new14"]
    assert len(legacy) == 38
    assert len(new14) == 14
