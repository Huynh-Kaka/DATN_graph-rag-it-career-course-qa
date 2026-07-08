"""D-05 statistics helpers."""

import pytest

from app.eval.statistics import (
    bootstrap_ci,
    compare_groups_effect,
    rank_biserial_effect_size,
)
from app.eval.quality_metrics import claim_grounding_rate


def test_bootstrap_ci_contains_mean():
    values = [0.2, 0.4, 0.6, 0.8]
    mean, lo, hi = bootstrap_ci(values, n_resamples=200, seed=1)
    assert lo <= mean <= hi


def test_rank_biserial_effect_size():
    x = [1.0, 1.0, 0.9]
    y = [0.1, 0.2, 0.0]
    r = rank_biserial_effect_size(x, y)
    assert r > 0.5


def test_claim_grounding_rate():
    allowed = {"python", "sql", "data scientist"}
    reply = "Python và SQL là nền tảng cho Data Scientist."
    rate = claim_grounding_rate(reply, allowed)
    assert rate == pytest.approx(1.0)
