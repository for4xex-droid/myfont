#!/usr/bin/env python3
"""P1-B 仮名数値ゲート CLI（コアは engine.kana.gate）。

例:
  python scripts/kana_gate.py shi
  python scripts/kana_gate.py to --params product_r1 --report gate_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kana numeric gate (review-loop B)")
    ap.add_argument("glyph_id", help="e.g. shi / i / to")
    ap.add_argument("--params", default="product_r1")
    ap.add_argument(
        "--expect-contours",
        type=int,
        default=None,
        help="override gate.expect_contours (migration only)",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=Path("gate_report.json"),
        help="write GateReport JSON (default: ./gate_report.json)",
    )
    ap.add_argument(
        "--yaml",
        type=Path,
        default=None,
        help="optional skeleton YAML path (fixtures); else registered glyph_id",
    )
    args = ap.parse_args(argv)

    from engine.kana.gate import run_gate, run_gate_path
    from engine.params import PARAM_SETS

    if args.params not in PARAM_SETS:
        print(f"error: unknown params {args.params}", file=sys.stderr)
        return 2

    if args.yaml is not None:
        report = run_gate_path(
            args.yaml,
            params=args.params,
            expect_contours_override=args.expect_contours,
        )
    else:
        report = run_gate(
            args.glyph_id,
            params=args.params,
            expect_contours_override=args.expect_contours,
        )

    if report.error:
        print(f"[FAIL] {report.error}")
    for c in report.checks:
        tag = "ok" if c.ok else "FAIL"
        print(f"[{tag}] {c.name}: {c.detail}")

    args.report.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"params={report.params} glyph={report.glyph_id} "
        f"coordinate_space={report.coordinate_space} "
        f"bearing={report.bearing_convention} "
        f"report={args.report} ok={report.ok}"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
