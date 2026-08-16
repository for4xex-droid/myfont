#!/usr/bin/env python3
"""核心20字（あ以外）の手描き足場: デスクトップPNG＋字ごとの空UFO。

あは描済みなので作らない。参照はラスタのみ（掟9）。
"""

from __future__ import annotations

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
SKIP = {"あ"}
DEFAULT_BG = "ipaex"
MANUAL_LIB = "com.mymincho.manual"


def core20() -> list[str]:
    text = (ROOT / "data" / "glyphset_p1_kana_core20.txt").read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def write_ufo(char: str, png: bytes, png_name: str) -> Path:
    from fontTools.misc.transform import Transform
    from ufoLib2 import Font
    from ufoLib2.objects.image import Image

    name = f"uni{ord(char):04X}"
    dest = UFO_ROOT / f"{char}.ufo"
    if dest.exists():
        import shutil

        shutil.rmtree(dest)

    font = Font()
    font.info.familyName = f"MyMincho-{char}"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = UPM
    font.info.ascender = ASCENDER
    font.info.descender = DESCENDER
    font.info.xHeight = 500
    font.info.capHeight = 800
    font.info.note = f"方式A足場。{char} ({name}) を3塗りで描く。なぞらない。"

    nd = font.newGlyph(".notdef")
    nd.width = UPM
    g = font.newGlyph(name)
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


def main() -> int:
    missing = [n for n, p in REFERENCE_FONTS.items() if not p.is_file()]
    if missing:
        print(f"error: missing fonts {missing}", file=sys.stderr)
        return 2

    DESKTOP.mkdir(parents=True, exist_ok=True)
    UFO_ROOT.mkdir(parents=True, exist_ok=True)
    bg_font = REFERENCE_FONTS[DEFAULT_BG]
    chars = [c for c in core20() if c not in SKIP]
    for char in chars:
        png = render_em_png(bg_font, char)
        desk = DESKTOP / f"{char}.png"
        desk.write_bytes(png)
        ufo = write_ufo(char, png, f"{char}_guide_{DEFAULT_BG}.png")
        print(f"{char} png={desk} ufo={ufo}")

    readme = DESKTOP / "README.txt"
    readme.write_text(
        "MyMincho 手描きガイド（核心20字のうち「あ」以外）\n"
        "\n"
        "各 PNG は IPAex のラスタ。位置の目安。なぞらない。\n"
        "Glyphs 用の空 UFO はリポジトリの fonts_out/manual_kana/ に字ごとにある。\n"
        "開き方: Glyphs で き.ufo を開く → uni 名のグリフをダブルクリック\n"
        "→ 表示 → 画像を表示 → 3塗り。合体しない。\n"
        "終わったら MyMincho.ufo にマージするか、「置いた」と伝える。\n"
        "し・い・と・つ・く はエンジン済み。描き直さなくてよい。\n",
        encoding="utf-8",
    )
    (UFO_ROOT / "README.md").write_text(
        "# 手描き用 1字 UFO（核心20字・あ以外）\n\n"
        "各フォルダは Glyphs で開ける空の UFO。背景は IPAex ラスタ（掟9）。\n"
        "デスクトップの画像は `~/Desktop/MyMincho手書き/`。\n"
        "し・い・と・つ・く はエンジン正本のまま。必要なら使わなくてよい。\n",
        encoding="utf-8",
    )
    print(f"desktop={DESKTOP} count={len(chars)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
