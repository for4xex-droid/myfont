#!/usr/bin/env python3
"""仮名と同じ切り方（重ね塗り・面）で漢字を捨てUFOに置く。正本は書かない。

エンジンのオフセットは使わない。来歴の議論の前に、混植が家族に見えるかを見る。
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
SCRATCH = ROOT / "proofs" / "mix" / "_scratch"
DEFAULT_OUT = ROOT / "proofs" / "mix"
MIX_TEXT = ROOT / "proofs" / "texts" / "mix.txt"
WIDTH = 1000
H = 58.0
V = 76.0

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engine" / "src"))

from make_mix_probe import (  # noqa: E402
    assert_throwaway_dest,
    copy_ship_ufo,
    missing_chars,
    render_sizes,
)


def _stroke(p0: tuple[float, float], p1: tuple[float, float], thick: float) -> list[tuple[float, float]]:
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length * thick / 2.0
    ny = dx / length * thick / 2.0
    return [
        (p0[0] + nx, p0[1] + ny),
        (p1[0] + nx, p1[1] + ny),
        (p1[0] - nx, p1[1] - ny),
        (p0[0] - nx, p0[1] - ny),
    ]


def _uroko(tip: tuple[float, float], direction: tuple[float, float], half: float) -> list[tuple[float, float]]:
    """仮名の止めに寄せた小さい右端。エンジン uroko=78 は使わない。"""
    dx, dy = direction
    length = math.hypot(dx, dy) or 1.0
    d = (dx / length, dy / length)
    up = (-d[1], d[0])
    peak = (tip[0] + d[0] * 18 + up[0] * (half + 22), tip[1] + d[1] * 18 + up[1] * (half + 22))
    a = (tip[0] + up[0] * half, tip[1] + up[1] * half)
    b = (tip[0] - up[0] * half + d[0] * 8, tip[1] - up[1] * half + d[1] * 8)
    return [a, peak, b]


def _draw(glyph, contours: list[list[tuple[float, float]]]) -> None:
    pen = glyph.getPen()
    for pts in contours:
        if len(pts) < 3:
            continue
        pen.moveTo(pts[0])
        for pt in pts[1:]:
            pen.lineTo(pt)
        pen.closePath()


def _new(font, name: str, code: int, contours: list[list[tuple[float, float]]]) -> None:
    if name in font:
        del font[name]
    g = font.newGlyph(name)
    g.unicodes = [code]
    g.width = WIDTH
    _draw(g, contours)
    g.lib["com.mymincho.mix_hand"] = True


def glyph_juu() -> list[list[tuple[float, float]]]:
    h = _stroke((190, 518), (810, 538), H)
    v = _stroke((498, 200), (508, 820), V)
    uroko = _uroko((810, 538), (1.0, 0.12), H / 2)
    return [h, v, uroko]


def glyph_ni() -> list[list[tuple[float, float]]]:
    top = _stroke((220, 640), (780, 656), H)
    bot = _stroke((190, 300), (820, 318), H + 4)
    return [top, _uroko((780, 656), (1.0, 0.1), H / 2), bot, _uroko((820, 318), (1.0, 0.08), H / 2)]


def glyph_san() -> list[list[tuple[float, float]]]:
    a = _stroke((240, 720), (760, 734), H - 4)
    b = _stroke((210, 510), (790, 524), H)
    c = _stroke((180, 280), (830, 298), H + 4)
    return [a, _uroko((760, 734), (1.0, 0.08), H / 2), b, _uroko((790, 524), (1.0, 0.08), H / 2), c, _uroko((830, 298), (1.0, 0.08), H / 2)]


def glyph_kuchi() -> list[list[tuple[float, float]]]:
    left = _stroke((260, 210), (268, 790), V)
    right = _stroke((730, 210), (738, 790), V)
    top = _stroke((250, 770), (750, 782), H)
    bot = _stroke((250, 220), (750, 234), H)
    return [left, right, top, bot, _uroko((750, 782), (1.0, 0.06), H / 2)]


def glyph_nichi() -> list[list[tuple[float, float]]]:
    left = _stroke((300, 210), (308, 790), V)
    right = _stroke((690, 210), (698, 790), V)
    top = _stroke((290, 770), (710, 782), H)
    mid = _stroke((300, 500), (700, 512), H - 6)
    bot = _stroke((290, 220), (710, 234), H)
    return [left, right, top, mid, bot]


def glyph_ta() -> list[list[tuple[float, float]]]:
    box = glyph_kuchi()
    mid_h = _stroke((270, 500), (730, 512), H - 6)
    mid_v = _stroke((498, 230), (506, 770), V - 8)
    return box + [mid_h, mid_v]


def glyph_naka() -> list[list[tuple[float, float]]]:
    box = glyph_kuchi()
    mid_v = _stroke((496, 160), (506, 840), V)
    return box + [mid_v]


def glyph_ei() -> list[list[tuple[float, float]]]:
    ten = _stroke((600, 800), (690, 760), 48)
    top = _stroke((250, 690), (720, 708), H)
    vert = _stroke((430, 220), (442, 700), V)
    left = _stroke((430, 520), (210, 240), V - 8)
    right = _stroke((440, 500), (800, 200), V - 4)
    return [ten, top, _uroko((720, 708), (1.0, 0.08), H / 2), vert, left, right]


GLYPHS = {
    "uni5341": (0x5341, glyph_juu),
    "uni4E8C": (0x4E8C, glyph_ni),
    "uni4E09": (0x4E09, glyph_san),
    "uni53E3": (0x53E3, glyph_kuchi),
    "uni65E5": (0x65E5, glyph_nichi),
    "uni7530": (0x7530, glyph_ta),
    "uni4E2D": (0x4E2D, glyph_naka),
    "uni6C38": (0x6C38, glyph_ei),
}


def write_kanji(ufo_dir: Path) -> int:
    import ufoLib2

    font = ufoLib2.Font.open(ufo_dir)
    for name, (code, builder) in GLYPHS.items():
        _new(font, name, code, builder())
    font.save()
    return len(GLYPHS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Throwaway hand-cut kanji mix probe")
    ap.add_argument("--scratch", type=Path, default=SCRATCH)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    scratch = assert_throwaway_dest(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    dest_ufo = scratch / "MyMincho-mix-hand.ufo"
    dest_otf = scratch / "MyMincho-mix-hand.otf"
    copy_ship_ufo(dest_ufo)
    n = write_kanji(dest_ufo)

    from engine.bridge import compile_otf

    compile_otf(dest_ufo, dest_otf, remove_overlaps=False)
    text = MIX_TEXT.read_text(encoding="utf-8").rstrip() + "\n"
    absent = missing_chars(dest_otf, text)
    if absent:
        print(f"error: missing {''.join(absent)}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    renders = render_sizes(dest_otf, text, args.out)
    for row in renders:
        src = Path(row["png"])
        dest = args.out / f"mix_hand_{row['size']}.png"
        shutil.copy2(src, dest)
        print(f"  {dest}")
    print(f"wrote {n} hand-cut kanji overlay glyphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
