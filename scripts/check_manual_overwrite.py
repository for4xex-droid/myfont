#!/usr/bin/env python3
"""手設計グリフがエンジン出力で上書きされていないか検査（掟13）。

Usage:
  python scripts/check_manual_overwrite.py --ufo fonts_out/MyMincho.ufo
  python scripts/check_manual_overwrite.py --engine-glyphs /tmp/engine_names.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = ROOT / "fonts_out" / "manual_glyphs.txt"


def load_manual(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line)
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", type=Path, default=DEFAULT_LIST)
    ap.add_argument("--engine-glyphs", type=Path, help="one glyph name per line from engine batch")
    ap.add_argument("--ufo", type=Path, help="UFO path; checks that manual glyphs exist")
    args = ap.parse_args(argv)

    if not args.manual.is_file():
        print(f"error: missing {args.manual}", file=sys.stderr)
        return 2
    if not args.engine_glyphs and not args.ufo:
        print("error: specify --engine-glyphs and/or --ufo (no-op pass forbidden)", file=sys.stderr)
        return 2

    manual = load_manual(args.manual)
    print(f"manual_glyphs: {len(manual)}")
    failed = False

    if args.engine_glyphs:
        engine = {
            ln.strip()
            for ln in args.engine_glyphs.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
        overlap = sorted(manual & engine)
        if overlap:
            print(f"REFUSED overwrite candidates ({len(overlap)}): {overlap[:20]}")
            failed = True
        else:
            print("ok: no overlap with engine glyph list")

    if args.ufo:
        glyphs_dir = args.ufo / "glyphs"
        if not glyphs_dir.is_dir():
            print(f"error: not a UFO glyphs dir: {glyphs_dir}", file=sys.stderr)
            return 2
        contents = args.ufo / "glyphs" / "contents.plist"
        if not contents.is_file():
            print(f"error: missing {contents} (cannot verify manual glyphs)", file=sys.stderr)
            return 1
        try:
            import plistlib

            with contents.open("rb") as f:
                mapping = plistlib.load(f)
        except (OSError, ValueError, TypeError, KeyError) as e:
            print(f"error: could not parse contents.plist: {e}", file=sys.stderr)
            return 1
        missing = [name for name in sorted(manual) if name not in mapping]
        if missing:
            print(f"missing in UFO ({len(missing)}): {missing[:20]}")
            failed = True
        else:
            print("ok: manual glyphs present in UFO contents.plist")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
