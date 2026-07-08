"""
Export frozen answer_quality gold subsets for regression / cohort eval.

Usage:
  python scripts/export_gold_subset.py --all
  python scripts/export_gold_subset.py --subset v21_38
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_SOURCE = PROJECT_ROOT / "data" / "eval" / "answer_quality_gold.jsonl"
OUT_DIR = PROJECT_ROOT / "data" / "eval"

# 14 seed IDs from original quality gold (frozen baseline14).
BASELINE14_IDS: frozenset[str] = frozenset(
    {
        "pf_ds_01",
        "pf_gd_01",
        "pf_devops_01",
        "cr_py_01",
        "cr_react_01",
        "cr_docker_01",
        "sg_mle_01",
        "sg_bi_01",
        "sg_bc_01",
        "rel_react_e2e_01",
        "rel_aws_cert_e2e_01",
        "rel_cka_e2e_01",
        "rel_django_e2e_01",
        "rel_empty_ansible_e2e_01",
    }
)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def filter_subset(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    if name == "baseline14":
        return [r for r in rows if str(r.get("id")) in BASELINE14_IDS]
    if name == "v21_38":
        return [
            r
            for r in rows
            if str(r.get("gold_cohort") or "") == "v21_legacy"
            or str(r.get("gold_source") or "").startswith("quality_gold_v2.1")
            or str(r.get("gold_cohort") or "") == "v21_38"
        ]
    if name == "v22_new14":
        return [
            r
            for r in rows
            if str(r.get("gold_cohort") or "") == "v22_new14"
            or str(r.get("gold_source") or "").startswith("quality_gold_v2.2")
        ]
    raise ValueError(f"Unknown subset: {name}")


def export_subset(
    source: Path,
    name: str,
    *,
    out_dir: Path = OUT_DIR,
) -> Path:
    rows = _load_rows(source)
    filtered = filter_subset(rows, name)
    out_path = out_dir / f"answer_quality_gold_{name}.jsonl"
    _write_rows(out_path, filtered)
    print(f"Wrote {len(filtered)} cases -> {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export answer_quality gold subsets")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--subset", choices=["baseline14", "v21_38", "v22_new14"])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"ERROR: missing {args.source}")
        raise SystemExit(1)

    if args.all:
        for name in ("baseline14", "v21_38", "v22_new14"):
            export_subset(args.source, name, out_dir=args.out_dir)
        return

    if not args.subset:
        parser.error("Specify --subset or --all")
    export_subset(args.source, args.subset, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
