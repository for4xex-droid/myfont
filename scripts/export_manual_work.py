#!/usr/bin/env python3
"""正本の手描き輪郭を作業 UFO へ書き戻す。ガイド画像は残す。

正本を Glyphs で開かない（巻き込み防止）。描くのは作業 UFO だけ。

例:
  engine/.venv/bin/python scripts/export_manual_work.py が じ づ ぞ ぼ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_SRC_ROOT = ROOT / "fonts_out" / "manual_kana"
MANUAL_LIB = "com.mymincho.manual"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receive_manual  # noqa: E402


def export_one(dest_font, work_path: Path, char: str) -> str:
    from ufoLib2 import Font

    name = receive_manual.uni_name(char)
    if name not in dest_font or len(dest_font[name]) == 0:
        raise RuntimeError(f"{name} has no contours in dest")
    if not receive_manual.is_ufo(work_path):
        raise RuntimeError(f"not a UFO: {work_path}")

    work = Font.open(work_path)
    if name not in work:
        wg = work.newGlyph(name)
        wg.unicodes = [ord(char)]
    else:
        wg = work[name]
    image = wg.image
    wg.clearContours()
    for contour in dest_font[name]:
        wg.appendContour(contour)
    wg.width = dest_font[name].width
    wg.unicodes = [ord(char)]
    wg.lib[MANUAL_LIB] = True
    if image is not None:
        wg.image = image
    work.save()
    return "exported"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Copy dest outlines into work UFOs")
    ap.add_argument("chars", nargs="+", help="hiragana, e.g. が じ")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--src-root", type=Path, default=DEFAULT_SRC_ROOT)
    args = ap.parse_args(argv)

    chars: list[str] = []
    for raw in args.chars:
        if len(raw) != 1:
            print(f"error: expected one char, got {raw!r}", file=sys.stderr)
            return 2
        if raw not in chars:
            chars.append(raw)
    if not receive_manual.is_ufo(args.dest):
        print(f"error: not a UFO: {args.dest}", file=sys.stderr)
        return 2

    from ufoLib2 import Font

    try:
        dest = Font.open(args.dest)
        for char in chars:
            work = args.src_root / f"{char}.ufo"
            action = export_one(dest, work, char)
            name = receive_manual.uni_name(char)
            glyph = dest[name]
            print(
                f"{char} {name} {action} contours={len(glyph)} "
                f"oncurve={receive_manual.oncurve_count(glyph)}"
            )
    except Exception as e:
        print(f"error: export failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
