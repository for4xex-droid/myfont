#!/usr/bin/env python3
"""方式A: 既存 UFO に空グリフ＋参照ラスタを足す。描済み輪郭は消さない。

例:
  engine/.venv/bin/python scripts/prepare_manual_kana.py き
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UFO_DIR = ROOT / "fonts_out" / "MyMincho.ufo"
MANUAL_LIB = "com.mymincho.manual"

from prepare_manual_a import (  # type: ignore
    ASCENDER,
    DESCENDER,
    REFERENCE_FONTS,
    UPM,
    render_em_png,
)


def _bg_dir(char: str) -> Path:
    return ROOT / "proofs" / "review" / char / "glyphs_bg"


def add_empty_glyph(char: str, *, default_bg: str) -> Path:
    from fontTools.misc.transform import Transform
    from ufoLib2 import Font
    from ufoLib2.objects.image import Image

    if len(char) != 1:
        raise ValueError(f"expected one char, got {char!r}")
    name = f"uni{ord(char):04X}"
    if not UFO_DIR.is_dir():
        raise FileNotFoundError(f"missing {UFO_DIR}; run prepare_manual_a.py first")

    font = Font.open(UFO_DIR)
    if name in font and len(font[name]) > 0:
        raise RuntimeError(f"{name} already has contours; refuse wipe")

    bg = _bg_dir(char)
    bg.mkdir(parents=True, exist_ok=True)
    images: dict[str, bytes] = {}
    for key, path in REFERENCE_FONTS.items():
        png = render_em_png(path, char)
        fname = f"{char}_guide_{key}.png"
        images[fname] = png
        (bg / fname).write_bytes(png)

    if name not in font:
        g = font.newGlyph(name)
    else:
        g = font[name]
    g.unicodes = [ord(char)]
    g.width = UPM
    g.lib[MANUAL_LIB] = True
    if not g.guidelines:
        g.appendGuideline({"name": "lsb", "x": 126, "y": 0, "angle": 90})
        g.appendGuideline({"name": "rsb_if_126", "x": 874, "y": 0, "angle": 90})
        g.appendGuideline({"name": "baseline", "x": 0, "y": 0, "angle": 0})
        g.appendGuideline({"name": "ascender", "x": 0, "y": ASCENDER, "angle": 0})
        g.appendGuideline({"name": "descender", "x": 0, "y": DESCENDER, "angle": 0})

    for fname, data in images.items():
        font.images[fname] = data
    g.image = Image(
        fileName=f"{char}_guide_{default_bg}.png",
        transformation=Transform(1, 0, 0, 1, 0, DESCENDER),
    )
    font.save()
    return bg / f"{char}_guide_{default_bg}.png"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add a manual kana glyph + raster guide")
    ap.add_argument("char", help="e.g. き")
    ap.add_argument("--bg", default="ipaex", choices=sorted(REFERENCE_FONTS))
    args = ap.parse_args(argv)
    try:
        png = add_empty_glyph(args.char, default_bg=args.bg)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"ufo={UFO_DIR}")
    print(f"glyph=uni{ord(args.char):04X} guide={png}")
    return 0


if __name__ == "__main__":
    # scripts/ を import パスに
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
