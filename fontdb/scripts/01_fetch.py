#!/usr/bin/env python3
"""T1: 5書体取得。欠落時は非ゼロ終了。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.acquire.fetch import fetch_all

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    doc = fetch_all(write_corpus=True)
    missing = doc["summary"]["missing"]
    if missing:
        logger.error("MISSING: %s", missing)
        return 1
    if doc["summary"]["acquired"] < 5:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
