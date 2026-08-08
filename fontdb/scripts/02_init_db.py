#!/usr/bin/env python3
"""T2: DDL 適用＋シード（冪等）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.ingest.db import connect, init_db
from fontdb.paths import DB_PATH


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="既存テーブルを落として作り直す")
    args = p.parse_args()
    conn = connect(DB_PATH)
    init_db(conn, reset=args.reset)
    conn.close()
    print("OK", DB_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
