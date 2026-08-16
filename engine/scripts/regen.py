#!/usr/bin/env python3
"""P0: 指定 params でコア字を一括再生成（union→refit→UFO→OTF）。

例:
  python scripts/regen.py --params product_r1
  python scripts/regen.py --params classic --out /tmp/mymincho_regen
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate core glyphs for a params set")
    ap.add_argument(
        "--params",
        required=True,
        help="PARAM_SETS name (e.g. product_r1, classic)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "output" / "regen",
        help="output root directory",
    )
    ap.add_argument(
        "--glyphs",
        nargs="+",
        default=None,
        help="glyph ids (default: CORE_GLYPHS)",
    )
    args = ap.parse_args()

    from engine.bridge import CORE_GLYPHS, build_temp_font, write_bridge_report
    from engine.params import PARAM_SETS, load_params_snapshot

    if args.params not in PARAM_SETS:
        print(
            f"unknown params: {args.params!r} (have {sorted(PARAM_SETS)})",
            file=sys.stderr,
        )
        return 1

    # P0: YAML 正本がある params だけ status / ロード健全性を確認
    ypath = ROOT / "params" / f"{args.params}.yaml"
    if ypath.is_file():
        try:
            import yaml as _yaml

            ydoc = _yaml.safe_load(ypath.read_text(encoding="utf-8")) or {}
            yst = str(ydoc.get("status", "")).lower()
            if args.params == "product_r1" and yst != "frozen":
                print(
                    f"warning: {ypath.name} status={yst!r} (expected frozen)",
                    file=sys.stderr,
                )
            load_params_snapshot(args.params)
        except (OSError, ValueError, FileNotFoundError) as e:
            print(f"warning: params yaml check: {e}", file=sys.stderr)

    out = args.out.resolve() / args.params
    out.mkdir(parents=True, exist_ok=True)
    ids = list(args.glyphs or CORE_GLYPHS.keys())
    if "a" in ids:
        print(
            "note: glyph 'a' is engine experiment only; "
            "shipping あ・う・え・お・か・き・け・こ・さ・す・せ・そ・た・ち・て "
            "are fonts_out/MyMincho.ufo (方式A)",
            file=sys.stderr,
        )
    print(f"regen params={args.params} glyphs={ids} out={out}")

    result = build_temp_font(
        args.params,
        glyph_ids=ids,
        out_root=out,
        family_name=f"MyMincho-{args.params}",
        keep_ufo=True,
    )
    report_path = write_bridge_report(result, out / "regen_report.json")
    summary = {
        "params": args.params,
        "glyphs": ids,
        "otf": str(result.otf_path),
        "ufo": str(result.ufo_dir),
        "fill_ok": bool(result.fill_check.get("ok")),
        "measure_juu": result.measure_juu,
        "report": str(report_path),
    }
    summary_path = out / "regen_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"otf={result.otf_path} fill_ok={summary['fill_ok']} "
        f"contrast={result.measure_juu.get('contrast_v_over_h') or result.measure_juu.get('value')}"
    )
    print(f"summary: {summary_path}")
    return 0 if summary["fill_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
