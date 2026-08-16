#!/usr/bin/env python3
"""手描き字の字間だけ直す。輪郭の形は変えない（平行移動＋幅）。

例:
  engine/.venv/bin/python scripts/set_manual_sidebearings.py せ
  engine/.venv/bin/python scripts/set_manual_sidebearings.py --out-of-band
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
TARGET_LSB = 126.0
TARGET_RSB = 118.0
LSB_BAND = (106.0, 146.0)
RSB_BAND = (98.0, 138.0)
ENGINE_CANONICAL = frozenset("いしとつくの")


def ink_bounds(glyph) -> tuple[float, float, float, float]:
    from fontTools.pens.boundsPen import BoundsPen

    bp = BoundsPen(None)
    glyph.draw(bp)
    if bp.bounds is None:
        raise ValueError("empty contours")
    return bp.bounds


def sidebearings(glyph) -> tuple[float, float, float]:
    xmin, _ymin, xmax, _ymax = ink_bounds(glyph)
    return xmin, glyph.width - xmax, xmax - xmin


def in_band(lsb: float, rsb: float) -> bool:
    return LSB_BAND[0] <= lsb <= LSB_BAND[1] and RSB_BAND[0] <= rsb <= RSB_BAND[1]


def set_sidebearings(glyph, *, lsb: float, rsb: float) -> None:
    xmin, _ymin, xmax, _ymax = ink_bounds(glyph)
    ink = xmax - xmin
    dx = lsb - xmin
    if dx != 0:
        for contour in glyph:
            for pt in contour:
                pt.x = pt.x + dx
        if glyph.image is not None:
            x_scale, xy, yx, y_scale, x_off, y_off = glyph.image.transformation
            glyph.image.transformation = (x_scale, xy, yx, y_scale, x_off + dx, y_off)
    glyph.width = int(round(lsb + ink + rsb))
    for guide in glyph.guidelines:
        if guide.name == "lsb":
            guide.x = lsb
        elif guide.name in ("rsb_if_126", "rsb"):
            guide.x = glyph.width - rsb


def _drawn_manual_chars(font) -> list[str]:
    out: list[str] = []
    for name in font.keys():
        if not name.startswith("uni") or len(name) != 7:
            continue
        try:
            ch = chr(int(name[3:], 16))
        except ValueError:
            continue
        glyph = font[name]
        if len(glyph) == 0:
            continue
        if not glyph.lib.get("com.mymincho.manual"):
            continue
        out.append(ch)
    return sorted(out, key=ord)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set manual kana LSB/RSB without reshaping")
    ap.add_argument("chars", nargs="*", help="hiragana to adjust, e.g. せ う")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--lsb", type=float, default=TARGET_LSB)
    ap.add_argument("--rsb", type=float, default=TARGET_RSB)
    ap.add_argument(
        "--out-of-band",
        action="store_true",
        help="adjust every drawn manual glyph outside the L/R band",
    )
    args = ap.parse_args(argv)

    if not args.dest.is_dir():
        print(f"error: missing dest UFO {args.dest}", file=sys.stderr)
        return 2
    if not args.chars and not args.out_of_band:
        print("error: pass chars or --out-of-band", file=sys.stderr)
        return 2
    for ch in args.chars:
        if len(ch) != 1:
            print(f"error: expected one char, got {ch!r}", file=sys.stderr)
            return 2
        if ch in ENGINE_CANONICAL:
            print(
                f"error: {ch} is engine-canonical; refuse sidebearing edit",
                file=sys.stderr,
            )
            return 2

    from ufoLib2 import Font

    try:
        font = Font.open(args.dest)
        targets = list(args.chars)
        if args.out_of_band:
            for ch in _drawn_manual_chars(font):
                if ch in ENGINE_CANONICAL:
                    continue
                name = f"uni{ord(ch):04X}"
                lsb, rsb, _ink = sidebearings(font[name])
                if not in_band(lsb, rsb) and ch not in targets:
                    targets.append(ch)
        if not targets:
            print("skip: nothing out of band")
            return 0
        changed = 0
        for ch in targets:
            name = f"uni{ord(ch):04X}"
            if name not in font or len(font[name]) == 0:
                print(f"error: {name} has no contours", file=sys.stderr)
                return 2
            before = sidebearings(font[name])
            set_sidebearings(font[name], lsb=args.lsb, rsb=args.rsb)
            after = sidebearings(font[name])
            print(
                f"{ch} {name} lsb {before[0]:.1f}->{after[0]:.1f} "
                f"rsb {before[1]:.1f}->{after[1]:.1f} "
                f"width {int(round(before[0] + before[2] + before[1]))}->{font[name].width}"
            )
            changed += 1
        font.save()
    except Exception as e:
        print(f"error: sidebearings failed: {e}", file=sys.stderr)
        return 1
    print(f"updated {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
