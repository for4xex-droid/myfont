#!/usr/bin/env python3
"""T6: コントラスト×うろこ散布図。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.ingest.db import connect
from fontdb.paths import DB_PATH, DEFAULT_PROFILE_ID, EXTRACTOR_VERSION
from fontdb.viz.scatter import plot_contrast_uroko

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not DB_PATH.exists():
        logger.error("DB がありません。scripts/04_glyph_metrics.py を先に実行してください")
        return 1
    conn = connect(DB_PATH)
    # 掟3: 同一 render_profile + extractor のみを同じ図に載せる
    rows = conn.execute(
        """
        SELECT f.family_id, fam.display_name,
               MAX(CASE WHEN p.probe_id='juu_contrast' THEN p.value END) AS contrast,
               MAX(CASE WHEN p.probe_id='san_uroko' THEN p.value END) AS uroko_rel
        FROM face f
        JOIN family fam ON fam.family_id = f.family_id
        JOIN probe_metric p ON p.face_id = f.face_id
        WHERE p.render_profile_id = ?
          AND p.extractor_version = ?
        GROUP BY f.family_id
        """,
        (DEFAULT_PROFILE_ID, EXTRACTOR_VERSION),
    ).fetchall()
    conn.close()
    if not rows:
        logger.error("該当 profile/extractor の probe がありません")
        return 1
    summary = [
        {
            "family_id": r[0],
            "display_name": r[1],
            "contrast": r[2],
            "uroko_rel": r[3],
        }
        for r in rows
    ]
    out = plot_contrast_uroko(summary)
    logger.info("wrote %s (profile=%s extractor=%s)", out, DEFAULT_PROFILE_ID, EXTRACTOR_VERSION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
