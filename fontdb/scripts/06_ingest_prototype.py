#!/usr/bin/env python3
"""T7 / T7+: engine 一時フォント化 → freetype 計測 → SQLite synthetic face 登録。

既定では OTF ビルド＋レポートに加え、fontdb.sqlite へ face_kind=synthetic で ingest する。
`--no-db` で従来どおりファイル成果物のみ。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC = PACKAGE_ROOT / "src"
ENGINE_SRC = PACKAGE_ROOT.parent / "engine" / "src"
for p in (SRC, ENGINE_SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="T7+ synthetic face ingest")
    ap.add_argument(
        "--params",
        nargs="+",
        default=None,
        help="param set names (default: all in synthetic_faces.yaml)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=PACKAGE_ROOT / "output" / "t7_bridge",
        help="JSON report / build staging directory",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: fontdb/data/db/fontdb.sqlite)",
    )
    ap.add_argument(
        "--reset-db",
        action="store_true",
        help="DB を全消去してから ingest（外部書体計測も消える）",
    )
    ap.add_argument(
        "--no-db",
        action="store_true",
        help="SQLite 登録をスキップ（T7 ファイルのみ）",
    )
    args = ap.parse_args()

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    if args.no_db:
        return _legacy_file_only(args.params or ["classic", "product_r1"], out)

    try:
        from fontdb.ingest.synthetic import ingest_synthetic_faces
        from fontdb.paths import DB_PATH, OUTPUT_DIR
    except ImportError as e:
        print(f"fontdb import failed: {e}", file=sys.stderr)
        return 1

    try:
        report = ingest_synthetic_faces(
            params_filter=args.params,
            db_path=args.db or DB_PATH,
            reset_db=args.reset_db,
            work_root=out / "_build",
        )
    except ImportError as e:
        print(
            "engine.bridge import failed. "
            "Install engine with: cd ../engine && pip install -e '.[join,bridge]'",
            file=sys.stderr,
        )
        print(e, file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError, KeyError) as e:
        print(f"T7+ ingest failed: {e}", file=sys.stderr)
        return 1

    summary_path = out / "t7_summary.json"
    summary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    db_report = OUTPUT_DIR / "t7_ingest_report.json"
    db_report.parent.mkdir(parents=True, exist_ok=True)
    db_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok_all = True
    for row in report.get("probe_summary") or []:
        print(
            f"  {row['family_id']}: juu={row.get('juu_status')} "
            f"contrast={row.get('contrast')} "
            f"san={row.get('san_status')} uroko={row.get('uroko_rel')}"
        )
        ok_all = ok_all and row.get("juu_status") == "ok"

    print(f"summary: {summary_path}")
    print(f"db report: {db_report}")
    print(f"db: {args.db or DB_PATH}")
    return 0 if ok_all else 2


def _legacy_file_only(params: list[str], out: Path) -> int:
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

    summary: dict = {"builds": [], "profile": "ft_1024_nohint_gray_v1", "db": False}
    ok_all = True
    for pname in params:
        print(f"=== T7 build {pname} (no-db) ===")
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
