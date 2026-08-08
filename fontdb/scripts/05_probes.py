#!/usr/bin/env python3
"""T5α: probe 結果を DB から表示（未計測なら 04 を先に実行）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.ingest.db import connect
from fontdb.paths import DB_PATH


def main() -> int:
    if not DB_PATH.exists():
        print("DB がありません。scripts/04_glyph_metrics.py を先に実行してください", file=sys.stderr)
        return 1
    conn = connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT face_id, probe_id, status, value, reason
        FROM probe_metric
        ORDER BY face_id, probe_id
        """
    ).fetchall()
    conn.close()
    if not rows:
        print("probe_metric が空です", file=sys.stderr)
        return 1
    san_ok = 0
    san_total = 0
    for face_id, probe_id, status, value, reason in rows:
        print(f"{face_id:40} {probe_id:14} {status:16} value={value}  {reason or ''}")
        if probe_id == "san_uroko":
            san_total += 1
            if status == "ok":
                san_ok += 1
    print(f"san_uroko ok={san_ok}/{san_total}")
    return 0 if san_ok == san_total and san_total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
