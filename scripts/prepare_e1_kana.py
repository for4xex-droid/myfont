#!/usr/bin/env python3
"""P-E1 残りひらがなの作業 UFO。既存は消さない。参照はラスタのみ（掟9）。

例:
  engine/.venv/bin/python scripts/prepare_e1_kana.py
  engine/.venv/bin/python scripts/prepare_e1_kana.py --no-desktop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_manual_a import (  # noqa: E402
    ASCENDER,
    DESCENDER,
    REFERENCE_FONTS,
    UPM,
    render_em_png,
)

DESKTOP = Path.home() / "Desktop" / "MyMincho手書き"
UFO_ROOT = ROOT / "fonts_out" / "manual_kana"
E1_LIST = ROOT / "data" / "glyphset_e1_hiragana.txt"
DEFAULT_BG = "ipaex"
MANUAL_LIB = "com.mymincho.manual"


def e1_chars() -> list[str]:
    return [ln.strip() for ln in E1_LIST.read_text(encoding="utf-8").splitlines() if ln.strip()]


def uni_name(char: str) -> str:
    return f"uni{ord(char):04X}"


def write_ufo(char: str, png: bytes, png_name: str) -> Path:
    from fontTools.misc.transform import Transform
    from ufoLib2 import Font
    from ufoLib2.objects.image import Image

    dest = UFO_ROOT / f"{char}.ufo"
    if dest.exists():
        raise FileExistsError(dest)

    font = Font()
    font.info.familyName = f"MyMincho-{char}"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = UPM
    font.info.ascender = ASCENDER
    font.info.descender = DESCENDER
    font.info.xHeight = 500
    font.info.capHeight = 800
    font.info.note = (
        f"P-E1 足場。{char} ({uni_name(char)})。なぞらない。"
        "濁点は Q3 のがじづぞぼに揃える。合体しない。"
    )

    nd = font.newGlyph(".notdef")
    nd.width = UPM
    g = font.newGlyph(uni_name(char))
    g.unicodes = [ord(char)]
    g.width = UPM
    g.lib[MANUAL_LIB] = True
    g.appendGuideline({"name": "lsb", "x": 126, "y": 0, "angle": 90})
    g.appendGuideline({"name": "rsb_if_126", "x": 874, "y": 0, "angle": 90})
    g.appendGuideline({"name": "baseline", "x": 0, "y": 0, "angle": 0})
    g.appendGuideline({"name": "ascender", "x": 0, "y": ASCENDER, "angle": 0})
    g.appendGuideline({"name": "descender", "x": 0, "y": DESCENDER, "angle": 0})
    font.images[png_name] = png
    g.image = Image(
        fileName=png_name,
        transformation=Transform(1, 0, 0, 1, 0, DESCENDER),
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    font.save(dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create E1 work UFOs without wiping existing")
    ap.add_argument("--no-desktop", action="store_true")
    args = ap.parse_args(argv)

    missing = [n for n, p in REFERENCE_FONTS.items() if n == DEFAULT_BG and not p.is_file()]
    if missing:
        print(f"error: missing fonts {missing}", file=sys.stderr)
        return 2

    bg_font = REFERENCE_FONTS[DEFAULT_BG]
    if not args.no_desktop:
        DESKTOP.mkdir(parents=True, exist_ok=True)
    UFO_ROOT.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for char in e1_chars():
        dest = UFO_ROOT / f"{char}.ufo"
        if dest.exists():
            print(f"skip {char}: {dest} exists")
            skipped += 1
            continue
        png = render_em_png(bg_font, char)
        if not args.no_desktop:
            (DESKTOP / f"{char}.png").write_bytes(png)
        write_ufo(char, png, f"{char}_guide_{DEFAULT_BG}.png")
        print(f"{char} ufo={dest}")
        created += 1
    print(f"created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
