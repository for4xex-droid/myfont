#!/usr/bin/env python3
"""T7 CLI: engine → 一時 UFO/OTF → fill/contrast レポート。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# editable install 前提。未インストール時は src を足す
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine.bridge import build_temp_font, write_bridge_report
from engine.params import PARAM_SETS


def main() -> int:
    ap = argparse.ArgumentParser(description="T7 temporary font bridge")
    ap.add_argument(
        "--params",
        default="classic",
        choices=sorted(PARAM_SETS.keys()),
        help="MinchoParams set / snapshot name",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "output" / "t7",
        help="output directory for UFO/OTF/report",
    )
    ap.add_argument(
        "--glyphs",
        default="juu,ni,ei",
        help="comma-separated glyph ids",
    )
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    glyphs = [g.strip() for g in args.glyphs.split(",") if g.strip()]
    result = build_temp_font(
        args.params,
        glyph_ids=glyphs,
        out_root=out / args.params,
        family_name=f"MyMinchoT7-{args.params}",
    )
    report = write_bridge_report(result, out / f"t7_{args.params}_report.json")
    print(f"otf: {result.otf_path}")
    print(f"fill_ok: {result.fill_check.get('ok')} ink={result.fill_check.get('ink_ratio')}")
    print(f"measure: {result.measure_juu.get('status')} {result.measure_juu.get('contrast_v_over_h') or result.measure_juu.get('value')}")
    print(f"report: {report}")
    return 0 if result.fill_check.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
