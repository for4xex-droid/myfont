#!/usr/bin/env python3
"""「あ」方式A足場: 空の uni3042 UFO ＋参照ラスタ背景（掟9: 輪郭は出さない）。

例:
  engine/.venv/bin/python scripts/prepare_manual_a.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UFO_DIR = ROOT / "fonts_out" / "MyMincho.ufo"
BG_DIR = ROOT / "proofs" / "review" / "a" / "glyphs_bg"
MANUAL_LIB = "com.mymincho.manual"

REFERENCE_FONTS: dict[str, Path] = {
    "source_han": ROOT / "fontdb/data/fonts/source_han_serif_jp-Regular.otf",
    "ipaex": ROOT / "fontdb/data/fonts/ipaex_mincho-Regular.ttf",
    "shippori": ROOT / "fontdb/data/fonts/shippori_mincho-Regular.ttf",
    "zen_old": ROOT / "fontdb/data/fonts/zen_old_mincho-Regular.ttf",
}

UPM = 1000
ASCENDER = 880
DESCENDER = -120
CANVAS = UPM  # y = DESCENDER .. ASCENDER


def render_em_png(font_path: Path, char: str) -> bytes:
    """参照字を EM キャンバスへラスタ化。アウトライン座標は読まない。"""
    import freetype
    import numpy as np
    from PIL import Image

    face = freetype.Face(str(font_path))
    face.set_char_size(UPM * 64)
    face.load_char(char, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if bm.width == 0 or bm.rows == 0:
        raise RuntimeError(f"empty raster: {font_path.name} {char!r}")
    ink = np.zeros((bm.rows, bm.width), dtype=np.uint8)
    buf = bytes(bm.buffer)
    for r in range(bm.rows):
        ink[r, :] = np.frombuffer(
            buf[r * bm.pitch : r * bm.pitch + bm.width], dtype=np.uint8
        )
    canvas = np.zeros((CANVAS, CANVAS), dtype=np.uint8)
    # 画像上端 = ascender。baseline は上から ASCENDER px。
    x0 = int(face.glyph.bitmap_left)
    y0 = int(ASCENDER - face.glyph.bitmap_top)
    x1, y1 = x0 + bm.width, y0 + bm.rows
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(CANVAS, x1), min(CANVAS, y1)
    if cx1 <= cx0 or cy1 <= cy0:
        raise RuntimeError(f"raster missed canvas: {font_path.name}")
    sx0, sy0 = cx0 - x0, cy0 - y0
    canvas[cy0:cy1, cx0:cx1] = np.maximum(
        canvas[cy0:cy1, cx0:cx1], ink[sy0 : sy0 + (cy1 - cy0), sx0 : sx0 + (cx1 - cx0)]
    )
    # 白地に中灰。空グリフ以外でも見える濃さ（なぞり用ではない）。
    page = 255 - (canvas.astype(np.uint16) * 140 // 255).astype(np.uint8)
    from io import BytesIO

    buf_out = BytesIO()
    Image.fromarray(page, mode="L").save(buf_out, format="PNG")
    return buf_out.getvalue()


def _has_drawn_contours(ufo_dir: Path) -> bool:
    glif = ufo_dir / "glyphs" / "uni3042.glif"
    if not glif.is_file():
        return False
    text = glif.read_text(encoding="utf-8")
    return "<point" in text


def build_ufo(images: dict[str, bytes], *, default_bg: str) -> None:
    from fontTools.misc.transform import Transform
    from ufoLib2 import Font
    from ufoLib2.objects.image import Image

    if UFO_DIR.exists():
        import shutil

        shutil.rmtree(UFO_DIR)

    font = Font()
    font.info.familyName = "MyMincho"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = UPM
    font.info.ascender = ASCENDER
    font.info.descender = DESCENDER
    font.info.xHeight = 500
    font.info.capHeight = 800
    font.info.openTypeOS2TypoAscender = ASCENDER
    font.info.openTypeOS2TypoDescender = DESCENDER
    font.info.openTypeOS2TypoLineGap = 0
    font.info.openTypeOS2WinAscent = ASCENDER
    font.info.openTypeOS2WinDescent = -DESCENDER
    font.info.note = (
        "方式A足場。uni3042 は手描き正本。背景PNGは参照ラスタガイドのみ（掟9）。"
    )

    nd = font.newGlyph(".notdef")
    nd.width = UPM

    g = font.newGlyph("uni3042")
    g.unicodes = [0x3042]
    g.width = UPM
    g.lib[MANUAL_LIB] = True
    g.appendGuideline({"name": "lsb", "x": 126, "y": 0, "angle": 90})
    g.appendGuideline({"name": "rsb_if_126", "x": 874, "y": 0, "angle": 90})
    g.appendGuideline({"name": "baseline", "x": 0, "y": 0, "angle": 0})
    g.appendGuideline({"name": "ascender", "x": 0, "y": ASCENDER, "angle": 0})
    g.appendGuideline({"name": "descender", "x": 0, "y": DESCENDER, "angle": 0})

    for name, data in images.items():
        font.images[name] = data
    fname = f"a_guide_{default_bg}.png"
    g.image = Image(
        fileName=fname,
        transformation=Transform(1, 0, 0, 1, 0, DESCENDER),
    )

    UFO_DIR.parent.mkdir(parents=True, exist_ok=True)
    font.save(UFO_DIR)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold manual あ UFO + raster guides")
    ap.add_argument("--force", action="store_true", help="wipe existing UFO even if drawn")
    ap.add_argument(
        "--bg",
        default="ipaex",
        choices=sorted(REFERENCE_FONTS),
        help="default background attached to uni3042",
    )
    args = ap.parse_args(argv)

    missing = [n for n, p in REFERENCE_FONTS.items() if not p.is_file()]
    if missing:
        print(f"error: missing reference fonts: {missing}", file=sys.stderr)
        return 2

    if UFO_DIR.is_dir() and _has_drawn_contours(UFO_DIR) and not args.force:
        print(
            f"error: {UFO_DIR} already has uni3042 contours; "
            "refuse wipe (pass --force to rebuild empty)",
            file=sys.stderr,
        )
        return 1

    BG_DIR.mkdir(parents=True, exist_ok=True)
    images: dict[str, bytes] = {}
    for name, path in REFERENCE_FONTS.items():
        png = render_em_png(path, "あ")
        fname = f"a_guide_{name}.png"
        images[fname] = png
        (BG_DIR / fname).write_bytes(png)
        print(f"bg {name}: {BG_DIR / fname}")

    import numpy as np
    from PIL import Image as PILImage

    stacks = [np.asarray(PILImage.open(BG_DIR / f"a_guide_{n}.png")) for n in REFERENCE_FONTS]
    avg = np.mean(np.stack(stacks, axis=0), axis=0).astype(np.uint8)
    from io import BytesIO

    buf = BytesIO()
    PILImage.fromarray(avg, mode="L").save(buf, format="PNG")
    images["a_guide_average.png"] = buf.getvalue()
    (BG_DIR / "a_guide_average.png").write_bytes(buf.getvalue())

    build_ufo(images, default_bg=args.bg)
    print(f"ufo={UFO_DIR}")
    print("next: open fonts_out/MyMincho.ufo in Glyphs, draw 3 fills on uni3042")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
