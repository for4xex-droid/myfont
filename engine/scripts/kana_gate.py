#!/usr/bin/env python3
"""P1-B 仮名スパイク用ゲート（G1: 輪郭数・再現性）。

例:
  python scripts/kana_gate.py shi
  python scripts/kana_gate.py shi --params product_r1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kana spike gate (G1)")
    ap.add_argument("glyph_id", help="e.g. shi")
    ap.add_argument("--params", default="product_r1")
    ap.add_argument(
        "--expect-contours",
        type=int,
        default=1,
        help="expected contour count after cleanup (し=1)",
    )
    args = ap.parse_args(argv)

    from engine.bridge import extract_contours_xy, is_kana_glyph
    from engine.extra_skeletons import all_characters
    from engine.join_solver import solve_glyph
    from engine.params import PARAM_SETS

    if args.params not in PARAM_SETS:
        print(f"error: unknown params {args.params}", file=sys.stderr)
        return 2
    chars = all_characters()
    if args.glyph_id not in chars:
        print(f"error: unknown glyph {args.glyph_id}", file=sys.stderr)
        return 2
    if not is_kana_glyph(args.glyph_id):
        print(f"error: {args.glyph_id} is not a kana skeleton", file=sys.stderr)
        return 2

    params = PARAM_SETS[args.params]
    r1 = solve_glyph(chars[args.glyph_id], params, apply_stage_a=False)
    r2 = solve_glyph(all_characters()[args.glyph_id], params, apply_stage_a=False)
    c1 = extract_contours_xy(r1.path)
    c2 = extract_contours_xy(r2.path)
    h1 = hashlib.sha256(json.dumps(c1).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(c2).encode()).hexdigest()

    failed = False
    if r1.after_cleanup != args.expect_contours:
        print(
            f"[FAIL] contours: got {r1.after_cleanup}, expect {args.expect_contours}"
        )
        failed = True
    else:
        print(f"[ok] contours={r1.after_cleanup}")

    if h1 != h2:
        print("[FAIL] reproducibility: contour hash mismatch")
        failed = True
    else:
        print(f"[ok] reproducible sha256={h1[:16]}…")

    print(f"params={args.params} glyph={args.glyph_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
