"""
D-05 — Pure-Python statistics helpers for ablation reports.

- Bootstrap 95% CI for means
- Rank-biserial effect size (Wilcoxon companion)
"""

from __future__ import annotations

import math
import random
from typing import Callable, Sequence


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Return (mean, lower, upper) bootstrap CI."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - ci) / 2.0
    lo_idx = max(0, int(math.floor(alpha * n_resamples)))
    hi_idx = min(n_resamples - 1, int(math.ceil((1.0 - alpha) * n_resamples)) - 1)
    point = sum(values) / n
    return point, means[lo_idx], means[hi_idx]


def rank_biserial_effect_size(x: Sequence[float], y: Sequence[float]) -> float:
    """
    Effect size r for two independent samples (rank-biserial approximation).

    r = 2(U / (n_x * n_y)) - 1 where U = # pairs with x > y + 0.5 ties.
    """
    if not x or not y:
        return 0.0
    greater = 0
    ties = 0
    for a in x:
        for b in y:
            if a > b:
                greater += 1
            elif a == b:
                ties += 1
    u = greater + 0.5 * ties
    return (2.0 * u / (len(x) * len(y))) - 1.0


def summarize_with_ci(
    values: Sequence[float],
    *,
    label: str = "metric",
) -> dict[str, float | str]:
    mean, lo, hi = bootstrap_ci(values)
    return {
        "label": label,
        "mean": round(mean, 4),
        "ci_lower": round(lo, 4),
        "ci_upper": round(hi, 4),
    }


def compare_groups_effect(
    baseline: Sequence[float],
    treatment: Sequence[float],
) -> dict[str, float]:
    return {
        "rank_biserial_r": round(rank_biserial_effect_size(treatment, baseline), 4),
        "mean_delta": round(
            (sum(treatment) / len(treatment) if treatment else 0.0)
            - (sum(baseline) / len(baseline) if baseline else 0.0),
            4,
        ),
    }
