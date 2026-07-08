"""
Pipeline fine-tune: export chat → synthetic → merge (không ghi đè lẫn nguồn).

Chạy:
  python scripts/build_ft_datasets.py
  python scripts/build_ft_datasets.py --per-career 8 --approved-only
  python scripts/build_ft_datasets.py --skip-synthetic
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chat-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ft_from_chat",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ft_from_synthetic",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data",
    )
    parser.add_argument("--per-career", type=int, default=4)
    parser.add_argument("--approved-only", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--skip-synthetic", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--val-ratio", type=float, default=0.15)
    args = parser.parse_args()

    py = sys.executable

    if not args.skip_export:
        export_cmd = [
            py,
            "scripts/export_chat_dataset.py",
            "--out-dir",
            str(args.chat_dir),
        ]
        if args.approved_only:
            export_cmd.append("--approved-only")
        try:
            _run(export_cmd)
        except subprocess.CalledProcessError:
            print("WARN: export failed (DATABASE_URL?). Continuing if other sources exist.")

    if not args.skip_synthetic:
        _run(
            [
                py,
                "scripts/build_synthetic_ft_data.py",
                "--out-dir",
                str(args.synthetic_dir),
                "--per-career",
                str(args.per_career),
            ]
        )

    if not args.skip_merge:
        _run(
            [
                py,
                "scripts/merge_ft_datasets.py",
                "--sources",
                str(args.chat_dir),
                str(args.synthetic_dir),
                "--out-dir",
                str(args.out_dir),
                "--val-ratio",
                str(args.val_ratio),
            ]
        )


if __name__ == "__main__":
    main()
