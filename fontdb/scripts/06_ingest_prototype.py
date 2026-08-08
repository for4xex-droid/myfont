#!/usr/bin/env python3
"""T7: engine 一時フォント化 bridge → freetype 計測レポート。

spike3 経路を engine.bridge へ昇格した実装。
classic / product_r1 を OTF 化し、fill チェックと juu_contrast を JSON に残す。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = PACKAGE_ROOT.parent / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))


def main() -> int:
    ap = argparse.ArgumentParser(description="T7 prototype/engine bridge ingest")
    ap.add_argument(
        "--params",
        nargs="+",
        default=["classic", "product_r1"],
        help="param set names to build",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=PACKAGE_ROOT / "output" / "t7_bridge",
        help="output directory",
    )
    args = ap.parse_args()

    try:
        from engine.bridge import build_temp_font, write_bridge_report
    except ImportError as e:
        print(
            "engine.bridge import failed. "
            "Install engine with: cd ../engine && pip install -e '.[join,bridge]'",
            file=sys.stderr,
        )
        print(e, file=sys.stderr)
        return 1

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"builds": [], "profile": "ft_1024_nohint_gray_v1"}
    ok_all = True
    for pname in args.params:
        print(f"=== T7 build {pname} ===")
        result = build_temp_font(
            pname,
            out_root=out / pname,
            family_name=f"MyMinchoT7-{pname}",
        )
        report_path = write_bridge_report(result, out / f"{pname}_report.json")
        entry = {
            "params": pname,
            "otf": str(result.otf_path),
            "fill_ok": bool(result.fill_check.get("ok")),
            "ink_ratio": result.fill_check.get("ink_ratio"),
            "measure_status": result.measure_juu.get("status"),
            "contrast_v_over_h": result.measure_juu.get("contrast_v_over_h")
            or result.measure_juu.get("value"),
            "report": str(report_path),
        }
        summary["builds"].append(entry)
        print(
            f"  otf={result.otf_path.name} fill_ok={entry['fill_ok']} "
            f"contrast={entry['contrast_v_over_h']}"
        )
        ok_all = ok_all and entry["fill_ok"]

    summary_path = out / "t7_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"summary: {summary_path}")
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(main())
