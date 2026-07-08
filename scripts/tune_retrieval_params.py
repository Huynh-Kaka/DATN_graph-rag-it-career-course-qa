"""
Optional grid search for RETRIEVAL_RRF_K and RETRIEVAL_RRF_POOL_SIZE.

Usage:
  python scripts/tune_retrieval_params.py --limit 50
  python scripts/tune_retrieval_params.py --k-values 40,60 --pool-values 40,60
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL = PROJECT_ROOT / "scripts" / "eval_retrieval.py"


def _run_eval(k: int, pool: int, *, limit: int | None) -> str:
    env = os.environ.copy()
    env["RETRIEVAL_RRF_K"] = str(k)
    env["RETRIEVAL_RRF_POOL_SIZE"] = str(pool)
    cmd = [sys.executable, str(EVAL), "--k", "5"]
    if limit:
        cmd.extend(["--limit", str(limit)])
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout + proc.stderr


def _parse_competency_recall(output: str) -> float | None:
    for line in output.splitlines():
        if "competency" in line.lower() and "recall" in line.lower():
            parts = line.replace("%", "").split()
            for p in parts:
                try:
                    return float(p)
                except ValueError:
                    continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid tune RRF K / pool size")
    parser.add_argument("--k-values", default="40,60,80")
    parser.add_argument("--pool-values", default="40,60,80")
    parser.add_argument("--limit", type=int, default=100, help="Max queries per run")
    args = parser.parse_args()

    k_vals = [int(x) for x in args.k_values.split(",") if x.strip()]
    pool_vals = [int(x) for x in args.pool_values.split(",") if x.strip()]

    results: list[tuple[int, int, float | None]] = []
    for k in k_vals:
        for pool in pool_vals:
            print(f"\n=== K={k} POOL={pool} ===")
            out = _run_eval(k, pool, limit=args.limit)
            recall = _parse_competency_recall(out)
            results.append((k, pool, recall))
            print(out[-2000:] if len(out) > 2000 else out)
            print(f"competency recall (parsed): {recall}")

    print("\n--- Summary ---")
    for k, pool, recall in sorted(results, key=lambda x: (x[2] or 0), reverse=True):
        print(f"K={k:3} POOL={pool:3}  competency_recall={recall}")


if __name__ == "__main__":
    main()
