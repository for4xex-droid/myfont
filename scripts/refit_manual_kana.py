#!/usr/bin/env python3
"""手描き仮名の節点再フィット（P-Q2）。し・く・っは拒否。失敗したら書かない。

例:
  engine/.venv/bin/python scripts/refit_manual_kana.py あ
  engine/.venv/bin/python scripts/refit_manual_kana.py あ --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
PROTECTED = frozenset("しくっ")
DEFAULT_TARGETS = "あぼたきさすそのる"
HAUSDORFF_MAX = 0.5
MANUAL_LIB = "com.mymincho.manual"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receive_manual  # noqa: E402
import set_manual_sidebearings as sidebearings  # noqa: E402

from engine.curve_fit import ContourPath, fit_closed_contour, hausdorff_path_to_polyline
from engine.curve_refit import _paths_self_intersect, _signed_area


def glyph_to_paths(glyph) -> list[ContourPath]:
    from fontTools.pens.recordingPen import RecordingPen

    pen = RecordingPen()
    glyph.draw(pen)
    paths: list[ContourPath] = []
    start = None
    segs: list[tuple] = []
    for op, args in pen.value:
        if op == "moveTo":
            if start is not None and segs:
                paths.append(ContourPath(start=start, segs=segs))
            start = (float(args[0][0]), float(args[0][1]))
            segs = []
        elif op == "lineTo":
            x, y = args[0]
            segs.append(("L", float(x), float(y)))
        elif op == "curveTo":
            c1, c2, end = args
            segs.append(
                (
                    "C",
                    float(c1[0]),
                    float(c1[1]),
                    float(c2[0]),
                    float(c2[1]),
                    float(end[0]),
                    float(end[1]),
                )
            )
        elif op == "qCurveTo":
            raise ValueError("quad contours are not supported")
    if start is not None and segs:
        paths.append(ContourPath(start=start, segs=segs))
    return paths


def write_paths(glyph, paths: list[ContourPath]) -> None:
    glyph.clearContours()
    pen = glyph.getPen()
    for path in paths:
        pen.moveTo(path.start)
        for seg in path.segs:
            if seg[0] == "L":
                pen.lineTo((seg[1], seg[2]))
            else:
                pen.curveTo((seg[1], seg[2]), (seg[3], seg[4]), (seg[5], seg[6]))
        pen.closePath()
    glyph.lib[MANUAL_LIB] = True


def oncurve_count(glyph) -> int:
    n = 0
    for contour in glyph:
        for pt in contour:
            if pt.type != "offcurve":
                n += 1
    return n


def refit_glyph(glyph, *, char: str) -> dict[str, Any]:
    """成功時だけ glyph を書き換える。失敗時は元のまま。"""
    before_n = len(glyph)
    before_on = oncurve_count(glyph)
    report: dict[str, Any] = {
        "char": char,
        "ok": False,
        "contours_before": before_n,
        "oncurve_before": before_on,
    }
    try:
        src_paths = glyph_to_paths(glyph)
        if len(src_paths) != before_n:
            raise ValueError(f"path extract {len(src_paths)} != contours {before_n}")
        fitted: list[ContourPath] = []
        worst = 0.0
        for path in src_paths:
            n_segs = max(1, len(path.segs))
            n_per = max(4, min(24, 120 // n_segs))
            sampled = path.sample(n_per_seg=n_per)
            new_path, meta = fit_closed_contour(
                sampled,
                max_error_upm=HAUSDORFF_MAX,
                corner_deg=30.0,
                max_anchors=48,
            )
            hd = hausdorff_path_to_polyline(new_path, sampled)
            if hd > HAUSDORFF_MAX + 1e-6:
                raise ValueError(f"hausdorff {hd:.4f} > {HAUSDORFF_MAX}")
            if _signed_area(new_path.on_curve_points()) < 0:
                raise ValueError("fitted contour is a hole")
            worst = max(worst, hd, float(meta["max_error"]))
            fitted.append(new_path)
        if len(fitted) != before_n:
            raise ValueError("contour count changed")
        if any(_signed_area(p.on_curve_points()) < 0 for p in fitted):
            raise ValueError("hole after fit")
        if _paths_self_intersect(fitted):
            raise ValueError("self-intersect after fit")
        write_paths(glyph, fitted)
        report.update(
            {
                "ok": True,
                "contours_after": len(glyph),
                "oncurve_after": oncurve_count(glyph),
                "hausdorff": worst,
                "holes": 0,
            }
        )
    except Exception as e:
        report["error"] = str(e)
        report["ok"] = False
        report["contours_after"] = len(glyph)
        report["oncurve_after"] = oncurve_count(glyph)
        report["holes"] = sum(1 for c in glyph if receive_manual.signed_area(c) < 0)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refit hand-drawn kana cubics (P-Q2)")
    ap.add_argument("chars", nargs="*", help="hiragana, e.g. あ る")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--all-targets", action="store_true", help=f"refit {DEFAULT_TARGETS}")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write dest (default is dry-run)",
    )
    args = ap.parse_args(argv)

    chars = list(args.chars)
    if args.all_targets:
        chars.extend(c for c in DEFAULT_TARGETS if c not in chars)
    if not chars:
        print("error: pass chars or --all-targets", file=sys.stderr)
        return 2
    for ch in chars:
        if len(ch) != 1:
            print(f"error: expected one char, got {ch!r}", file=sys.stderr)
            return 2
        if ch in PROTECTED:
            print(f"error: refuse to refit protected {ch}", file=sys.stderr)
            return 2
    if not args.dest.is_dir() or not receive_manual.is_ufo(args.dest):
        print(f"error: missing dest UFO {args.dest}", file=sys.stderr)
        return 2

    from ufoLib2 import Font

    dest = Font.open(args.dest)
    failed = False
    changed = False
    for ch in chars:
        name = f"uni{ord(ch):04X}"
        if name not in dest or len(dest[name]) == 0:
            print(f"error: {name} has no contours", file=sys.stderr)
            return 2
        print(f"... {ch} {name} contours={len(dest[name])} oncurve={oncurve_count(dest[name])}", flush=True)
        report = refit_glyph(dest[name], char=ch)
        status = "ok" if report["ok"] else "FAIL"
        extra = ""
        if report["ok"]:
            extra = (
                f" oncurve {report['oncurve_before']}->{report['oncurve_after']} "
                f"hd={report['hausdorff']:.3f}"
            )
            if args.apply:
                sidebearings.set_sidebearings(
                    dest[name],
                    lsb=sidebearings.TARGET_LSB,
                    rsb=sidebearings.TARGET_RSB,
                )
                changed = True
        else:
            failed = True
            extra = f" {report.get('error', '')}"
        print(f"[{status}] {ch} {name}{extra}")

    if args.apply and changed and not failed:
        dest.save()
        keep = {"contents.plist"}
        for ch in chars:
            keep.add(receive_manual.glif_relpath(args.dest, f"uni{ord(ch):04X}"))
        restored = receive_manual.restore_other_from_head(args.repo, args.dest, keep)
        print(f"applied restored={len(restored)}")
    elif args.apply and failed:
        print("error: refuse apply; at least one glyph failed", file=sys.stderr)
        return 1
    elif not args.apply:
        print("dry-run (pass --apply to write)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
