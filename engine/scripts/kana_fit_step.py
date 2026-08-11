#!/usr/bin/env python3
"""1字ぶんの帯合わせステップ（中断耐性）。

長時間サブエージェント1本に頼らず、毎回このスクリプトで
gate + 参照スカラーを測り JSON に残す。再開時はこのログを見て続きから。

例:
  python scripts/kana_fit_step.py ku --char く
  python scripts/kana_fit_step.py ku --char く --regen
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO = ROOT.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One resilient band-fit step")
    ap.add_argument("glyph_id")
    ap.add_argument("--char", required=True, help="e.g. く")
    ap.add_argument("--params", default="product_r1")
    ap.add_argument(
        "--regen",
        action="store_true",
        help="regen this glyph into the shared OTF before measure",
    )
    ap.add_argument(
        "--render",
        action="store_true",
        help="also kana_render single.png",
    )
    ap.add_argument(
        "--log-dir",
        type=Path,
        default=REPO / "proofs" / "review",
        help="append-only JSONL log root",
    )
    args = ap.parse_args(argv)

    py = str(ROOT / ".venv" / "bin" / "python")
    log_dir = args.log_dir / args.glyph_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "band_fit.jsonl"

    record: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "glyph_id": args.glyph_id,
        "char": args.char,
        "params": args.params,
    }

    if args.regen:
        code, out = _run(
            [
                py,
                "scripts/regen.py",
                "--params",
                args.params,
                "--glyphs",
                args.glyph_id,
            ]
        )
        record["regen_ok"] = code == 0
        if code != 0:
            record["regen_tail"] = out[-500:]
            log_path.open("a", encoding="utf-8").write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )
            print(out)
            print(f"status=regen_fail log={log_path}")
            return 2

    # gate
    report_path = log_dir / "gate_report.json"
    code, out = _run(
        [
            py,
            "scripts/kana_gate.py",
            args.glyph_id,
            "--params",
            args.params,
            "--report",
            str(report_path),
        ]
    )
    record["gate_ok"] = code == 0
    record["gate_exit"] = code
    if report_path.is_file():
        try:
            gate_doc = json.loads(report_path.read_text(encoding="utf-8"))
            record["gate"] = gate_doc
            # Phase 0b: 観測は合否と分離してトップレベルにも抜粋
            obs = gate_doc.get("observe")
            if isinstance(obs, dict):
                record["observe"] = {
                    "points_after": (obs.get("outline") or {}).get("points_after"),
                    "anchor_count": (obs.get("outline") or {}).get("anchor_count"),
                    "curvature_p95": (obs.get("curvature") or {}).get(
                        "curvature_p95"
                    ),
                    "min_radius_upm": (obs.get("curvature") or {}).get(
                        "min_radius_upm"
                    ),
                }
        except json.JSONDecodeError:
            record["gate"] = None

    # ref compare (needs OTF; skip measure if missing)
    otf = ROOT / "output" / "regen" / args.params / f"MyMincho-{args.params}-Regular.otf"
    if otf.is_file():
        code2, out2 = _run(
            [py, "scripts/kana_ref_compare.py", args.char, "--font", str(otf)]
        )
        record["ref_exit"] = code2
        # parse OURS line
        ours = None
        band: dict[str, str] = {}
        for line in out2.splitlines():
            if line.startswith("OURS"):
                parts = line.split()
                # OURS aspect topL topR botCX centroid ink
                if len(parts) >= 7:
                    ours = {
                        "aspect_w_over_h": float(parts[1]),
                        "top_ink_left_frac": float(parts[2]),
                        "top_ink_right_frac": float(parts[3]),
                        "bottom_cx_frac": float(parts[4]),
                        "centroid_y_frac": float(parts[5]),
                        "ink_density": float(parts[6]),
                    }
            if line.strip().startswith("aspect_w_over_h:"):
                band["aspect_w_over_h"] = line.split(":", 1)[1].strip()
            for key in (
                "top_ink_left_frac",
                "top_ink_right_frac",
                "bottom_cx_frac",
                "centroid_y_frac",
                "ink_density",
            ):
                if line.strip().startswith(f"{key}:"):
                    band[key] = line.split(":", 1)[1].strip()
        record["ours"] = ours
        record["reference_band"] = band
    else:
        record["ref_exit"] = None
        record["ours"] = None
        record["note"] = f"OTF missing: {otf} (pass --regen)"

    if args.render and otf.is_file():
        code3, _ = _run(
            [py, "scripts/kana_render.py", "--glyph", args.glyph_id, "--params", args.params]
        )
        record["render_ok"] = code3 == 0

    # width sanity from YAML (prevent shi-style blowouts)
    from engine.kana import load_kana_skeleton, skeletons_dir

    _gid, strokes, _meta = load_kana_skeleton(skeletons_dir() / f"{args.glyph_id}.yaml")
    hws = []
    for s in strokes:
        if s.width_keys:
            hws.extend(float(w) for _, w in s.width_keys)
    record["width_hw_min"] = min(hws) if hws else None
    record["width_hw_max"] = max(hws) if hws else None
    record["width_ok"] = (
        bool(hws) and min(hws) >= 3.0 and max(hws) <= 40.0 and hws[0] <= 18.0
        if hws
        else False
    )

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # human-readable summary
    print(f"glyph={args.glyph_id} gate_ok={record['gate_ok']} width_ok={record['width_ok']}")
    if record.get("ours"):
        o = record["ours"]
        print(
            "ours: "
            f"aspect={o['aspect_w_over_h']} topL={o['top_ink_left_frac']} "
            f"topR={o['top_ink_right_frac']} botCX={o['bottom_cx_frac']} "
            f"cy={o['centroid_y_frac']} ink={o['ink_density']}"
        )
    if record.get("reference_band"):
        print("band:", record["reference_band"])
    print(f"log={log_path}")

    # exit: 0=gate+width ok, 1=gate/width fail, 2=tool fail
    if not record.get("gate_ok") or not record.get("width_ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
