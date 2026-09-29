"""内部用 UFO。バージョンは 0.xxx。ライセンス URL は入れない。"""

from __future__ import annotations

import shutil
from pathlib import Path

import ufoLib2

from engine.curve_fit import ContourPath
from engine.geometry import UPM
from engine.latin.glyphset import glyph_name
from engine.latin.style import Style

# 仕様のファミリー名。引き渡し前の内部ビルドなので version は 0.xxx。
FAMILY_NAMES = {
    "modern": "Someiro Modern",
    "classic": "Someiro Classic",
    "chic": "Someiro Chic",
    "pop": "Someiro Pop",
}
VERSION = "Version 0.001"
_COPYRIGHT = "Copyright 2026 Motivation Studio LLC. All rights reserved."


def _draw(glyph, path: ContourPath) -> None:
    pen = glyph.getPen()
    pen.moveTo(path.start)
    for seg in path.segs:
        if seg[0] == "L":
            pen.lineTo((seg[1], seg[2]))
        else:
            pen.curveTo((seg[1], seg[2]), (seg[3], seg[4]), (seg[5], seg[6]))
    pen.closePath()


def write_ufo(
    style: Style,
    glyphs: list[tuple[str, int, float, tuple[ContourPath, ...]]],
    out_dir: Path,
) -> Path:
    """glyphs は (文字, unicode, advance, 輪郭)。"""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    font = ufoLib2.Font()
    info = font.info
    family = FAMILY_NAMES[style.name]
    info.familyName = family
    info.styleName = "Regular"
    info.unitsPerEm = UPM
    info.ascender = int(style.vertical["ascender"])
    info.descender = int(style.vertical["descender"])
    info.capHeight = int(style.cap_height)
    info.xHeight = int(style.cap_height)
    info.openTypeOS2TypoAscender = info.ascender
    info.openTypeOS2TypoDescender = info.descender
    info.openTypeOS2TypoLineGap = 0
    info.openTypeOS2WinAscent = info.ascender
    info.openTypeOS2WinDescent = abs(info.descender)
    info.openTypeOS2VendorID = "MTVS"
    info.openTypeOS2Type = []
    info.versionMajor = 0
    info.versionMinor = 1
    info.openTypeNameVersion = VERSION
    info.copyright = _COPYRIGHT
    info.note = "WIP internal build"
    font.lib["myfont.latin.wip"] = True
    font.lib["myfont.latin.styleId"] = style.style_id
    font.lib["myfont.latin.styleHash"] = style.content_hash

    notdef = font.newGlyph(".notdef")
    notdef.width = UPM
    for char, code, advance, paths in glyphs:
        glyph = font.newGlyph(glyph_name(char))
        glyph.unicodes = [code]
        glyph.width = round(advance)
        for path in paths:
            _draw(glyph, path)
    font.save(out_dir)
    return out_dir
