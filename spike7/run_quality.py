#!/usr/bin/env python3
"""B. 代表字の結合レンダリング（KAGE骨格→写像→classic肉付け→SVG/PNG）。"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipeline import load_index, render_char  # noqa: E402

OUT = ROOT / "output"
QUALITY_CHARS = list("永国十木東語人山口海")  # 10字: 画数帯のバラつき


def main() -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    index = load_index()
    out_dir = OUT / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for ch in QUALITY_CHARS:
        print(f"=== {ch} U+{ord(ch):04X} ===")
        r = render_char(ch, index, out_dir)
        status = "OK" if r.get("render_ok") else f"NG:{r.get('error')}"
        print(
            f"  {status} flat={r.get('n_flat')} mapped={r.get('n_mapped')} "
            f"fb={r.get('fallback_total')} depth={r.get('depth')}"
        )
        if r.get("svg"):
            print(f"  svg={r['svg']}")
            print(f"  png={r['png']}")
        rows.append(r)

    report = {
        "chars": QUALITY_CHARS,
        "results": rows,
        "ok_count": sum(1 for r in rows if r.get("render_ok")),
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nquality: {report['ok_count']}/{len(QUALITY_CHARS)} OK")
    return 0 if report["ok_count"] == len(QUALITY_CHARS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
