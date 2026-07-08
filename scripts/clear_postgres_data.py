"""
Xóa toàn bộ dữ liệu PostgreSQL (chat, profile, tư vấn) — giữ nguyên schema.

Nhanh hơn reset_db_v2.py vì không DROP/CREATE bảng.

Chạy:
  python scripts/clear_postgres_data.py          # hỏi xác nhận
  python scripts/clear_postgres_data.py --yes    # bỏ qua xác nhận
  python scripts/clear_postgres_data.py --count  # chỉ đếm, không xóa
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)


def _print_counts(counts: dict[str, int]) -> None:
    total = sum(counts.values())
    for table, n in counts.items():
        print(f"  {table}: {n}")
    print(f"  Total: {total} rows")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Xóa dữ liệu PostgreSQL (giữ schema)")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Xóa ngay, không hỏi xác nhận",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="Chỉ đếm số dòng, không xóa",
    )
    args = parser.parse_args()

    from app.db.engine import database_enabled
    from app.db.maintenance import clear_all_postgres_data, count_postgres_rows

    if not database_enabled():
        print("ERROR: DATABASE_URL chưa được cấu hình trong .env")
        sys.exit(1)

    counts = await count_postgres_rows()
    print("Current row counts:")
    _print_counts(counts)

    if args.count:
        return

    if sum(counts.values()) == 0:
        print("OK: Database already empty.")
        return

    if not args.yes:
        answer = input("\nDelete all rows above? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return

    removed = await clear_all_postgres_data()
    print("\nOK: Deleted rows:")
    _print_counts(removed)


if __name__ == "__main__":
    asyncio.run(main())
