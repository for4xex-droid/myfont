#!/usr/bin/env python3
"""T4/T5α: glyph_metric + probe を一括計測して DB に格納。"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.paths import OUTPUT_DIR
from fontdb.pipeline import run_measure

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run_measure(reset_db=True, save_rasters=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "measure_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    ok_glyphs = sum(
        1
        for face in report["faces"].values()
        for g in face["glyphs"].values()
        if g["status"] == "ok"
    )
    logger.info("glyph ok count=%s", ok_glyphs)
    logger.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
