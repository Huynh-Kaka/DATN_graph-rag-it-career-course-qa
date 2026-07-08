"""
Gộp nhiều nguồn fine-tune JSONL (chat + synthetic), dedup và chia lại train/val.

Chạy:
  python scripts/merge_ft_datasets.py
  python scripts/merge_ft_datasets.py --sources data/ft_from_chat data/ft_from_synthetic --out-dir data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from ft_dataset_utils import INTENTS, ft_paths, merge_sources, write_ft_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge ft_generator JSONL sources into canonical data/ files."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        type=Path,
        default=[
            PROJECT_ROOT / "data" / "ft_from_chat",
            PROJECT_ROOT / "data" / "ft_from_synthetic",
        ],
        help="Directories containing ft_generator_*.jsonl (train+val combined per source)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Output directory for merged ft_generator_* files (Colab input)",
    )
    parser.add_argument("--val-ratio", type=float, default=0.15)
    args = parser.parse_args()

    existing = [p for p in args.sources if p.is_dir()]
    if not existing:
        print("ERROR: no source directories found:", args.sources)
        sys.exit(1)
    if len(existing) < len(args.sources):
        missing = [p for p in args.sources if not p.is_dir()]
        print("WARN: skipping missing sources:", ", ".join(str(p) for p in missing))

    merged = merge_sources(existing, val_ratio=args.val_ratio)
    for intent in INTENTS:
        train, val = merged[intent]
        train_path, val_path = ft_paths(args.out_dir, intent)
        write_ft_jsonl(train_path, train)
        write_ft_jsonl(val_path, val)
        print(f"{intent}: train={len(train)} val={len(val)} -> {args.out_dir}")


if __name__ == "__main__":
    main()
