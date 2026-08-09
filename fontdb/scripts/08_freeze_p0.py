#!/usr/bin/env python3
"""P0完成: product_r1 を design_param_snapshot に frozen 登録し face に紐付ける。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.ingest.db import connect, init_db
from fontdb.ingest.snapshots import freeze_product_r1, load_params_doc
from fontdb.paths import DB_PATH, OUTPUT_DIR

logger = logging.getLogger(__name__)

DEFAULT_LINK_FACES = [
    "mymincho_t7_product_r1_regular",
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Freeze product_r1 as P0 design_param_snapshot")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--reset-db",
        action="store_true",
        help="危険: DB全消去（通常は使わない）",
    )
    ap.add_argument(
        "--link-faces",
        nargs="*",
        default=DEFAULT_LINK_FACES,
        help="紐付ける face_id（存在するものだけ）",
    )
    args = ap.parse_args()

    doc = load_params_doc("product_r1")
    if str(doc.get("status", "")).lower() != "frozen":
        logger.error(
            "engine/params/product_r1.yaml status が frozen ではありません: %r",
            doc.get("status"),
        )
        return 1

    db = args.db or DB_PATH
    conn = connect(db)
    init_db(conn, reset=args.reset_db)
    meta = freeze_product_r1(conn, link_face_ids=list(args.link_faces or []))
    conn.commit()

    row = conn.execute(
        """SELECT snapshot_id, status, params_sha256, frozen_at
           FROM design_param_snapshot WHERE snapshot_id='product_r1'"""
    ).fetchone()
    links = conn.execute(
        """SELECT face_id FROM face_param_link WHERE snapshot_id='product_r1'
           ORDER BY face_id"""
    ).fetchall()
    conn.close()

    report = {
        "ok": True,
        "snapshot": {
            "snapshot_id": row[0],
            "status": row[1],
            "params_sha256": row[2],
            "frozen_at": row[3],
        },
        "linked_faces": [r[0] for r in links],
        "meta": meta,
        "design_rules": "docs/design_rules.md",
    }
    out = OUTPUT_DIR / "p0_freeze_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "frozen product_r1 sha=%s links=%s",
        row[2][:12],
        report["linked_faces"],
    )
    logger.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
