"""
Validate fine-tune JSONL before Colab training.

Chạy: python scripts/validate_ft_jsonl.py data/ft_generator_pathfinding_train.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_COURSE_IN_TEXT = re.compile(r"\b[A-Z]{2,}[-_]?\d*\b")


def validate_file(path: Path) -> int:
    errors = 0
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Line {i}: invalid JSON — {exc}")
                errors += 1
                continue

            messages = obj.get("messages")
            if not isinstance(messages, list) or len(messages) < 3:
                print(f"Line {i}: need messages[system,user,assistant]")
                errors += 1
                continue

            roles = [m.get("role") for m in messages]
            if roles[:3] != ["system", "user", "assistant"]:
                print(f"Line {i}: expected roles system,user,assistant got {roles[:3]}")
                errors += 1

            user_content = messages[1].get("content") or ""
            if "## Dữ liệu Neo4j" not in user_content:
                print(f"Line {i}: user prompt missing Neo4j block")
                errors += 1

    if errors == 0:
        print(f"OK: {path}")
    else:
        print(f"FAIL: {path} — {errors} error(s)")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    total = sum(validate_file(p) for p in args.paths)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
