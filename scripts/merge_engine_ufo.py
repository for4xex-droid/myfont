#!/usr/bin/env python3
"""エンジンUFOを fonts_out 正本へマージ。手描きグリフは上書きしない（掟13）。

例:
  engine/.venv/bin/python scripts/merge_engine_ufo.py \\
    --engine engine/output/regen/product_r1/MyMincho-product_r1.ufo \\
    --dest fonts_out/MyMincho.ufo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_MANUAL = ROOT / "fonts_out" / "manual_glyphs.txt"
MANUAL_LIB = "com.mymincho.manual"


def load_drawn(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line)
    return names


def _is_protected(dest_font, name: str, drawn: set[str]) -> bool:
    if name not in dest_font:
        return name in drawn
    g = dest_font[name]
    if g.lib.get(MANUAL_LIB):
        return True
    if name in drawn:
        return True
    if len(g) > 0:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Merge engine UFO into manual UFO")
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    args = ap.parse_args(argv)

    if not args.engine.is_dir():
        print(f"error: missing engine UFO {args.engine}", file=sys.stderr)
        return 2
    if not args.dest.is_dir():
        print(f"error: missing dest UFO {args.dest}", file=sys.stderr)
        return 2

    from ufoLib2 import Font

    drawn = load_drawn(args.manual)
    engine = Font.open(args.engine)
    dest = Font.open(args.dest)
    skipped: list[str] = []
    copied = 0
    for name in engine.keys():
        if name == ".notdef":
            continue
        if _is_protected(dest, name, drawn):
            skipped.append(name)
            continue
        dest[name] = engine[name].copy()
        copied += 1
    dest.save()
    print(f"copied={copied} skipped={skipped}")
    if "uni3042" in engine and "uni3042" not in skipped:
        print("error: uni3042 was not protected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
