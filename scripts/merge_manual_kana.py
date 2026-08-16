#!/usr/bin/env python3
"""作業 UFO を出荷正本へ1字コピー。描済み dest は消さない。

例:
  engine/.venv/bin/python scripts/merge_manual_kana.py さ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_SRC_ROOT = ROOT / "fonts_out" / "manual_kana"
MANUAL_LIB = "com.mymincho.manual"
# エンジンのまま残す字。空 = 核心字は手描きに切替済み。
ENGINE_CANONICAL = frozenset()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Merge one hand-drawn kana UFO into dest")
    ap.add_argument("char", help="one hiragana character, e.g. さ")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--src-root", type=Path, default=DEFAULT_SRC_ROOT)
    ap.add_argument(
        "--force",
        action="store_true",
        help="replace dest even if it already has contours",
    )
    args = ap.parse_args(argv)

    if len(args.char) != 1:
        print(f"error: expected one char, got {args.char!r}", file=sys.stderr)
        return 2
    if args.char in ENGINE_CANONICAL:
        print(
            f"error: {args.char} is engine-canonical; refuse work-UFO merge",
            file=sys.stderr,
        )
        return 2
    src = args.src_root / f"{args.char}.ufo"
    if not src.is_dir():
        print(f"error: missing work UFO {src}", file=sys.stderr)
        return 2
    if not args.dest.is_dir():
        print(f"error: missing dest UFO {args.dest}", file=sys.stderr)
        return 2

    from ufoLib2 import Font

    name = f"uni{ord(args.char):04X}"
    try:
        work = Font.open(src)
        dest = Font.open(args.dest)
        if name not in work or len(work[name]) == 0:
            print(f"error: {src} has no contours for {name}", file=sys.stderr)
            return 2
        if name in dest and len(dest[name]) > 0 and not args.force:
            print(f"skip {name}: dest already drawn ({len(dest[name])} contours)")
            return 0
        dest[name] = work[name].copy()
        dest[name].lib[MANUAL_LIB] = True
        dest[name].unicodes = [ord(args.char)]
        dest.save()
    except Exception as e:
        print(f"error: merge failed: {e}", file=sys.stderr)
        return 1
    print(f"merged {args.char} {name} contours={len(dest[name])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
