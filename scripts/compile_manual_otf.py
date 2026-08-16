#!/usr/bin/env python3
"""手描き重ね塗りUFOを OTF 化。交差は union しない。

例:
  engine/.venv/bin/python scripts/compile_manual_otf.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_OTF = ROOT / "fonts_out" / "build" / "MyMincho.otf"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compile overlay UFO without removing overlaps")
    ap.add_argument("--ufo", type=Path, default=DEFAULT_UFO)
    ap.add_argument("--otf", type=Path, default=DEFAULT_OTF)
    args = ap.parse_args(argv)

    if not args.ufo.is_dir():
        print(f"error: missing UFO {args.ufo}", file=sys.stderr)
        return 2
    ufo = args.ufo.resolve()
    otf = args.otf.resolve()
    if otf == ufo or ufo in otf.parents:
        print(f"error: refuse to write OTF inside UFO {ufo}", file=sys.stderr)
        return 2

    from engine.bridge import compile_otf

    try:
        compile_otf(ufo, otf, remove_overlaps=False)
    except Exception as e:
        print(f"error: compile failed: {e}", file=sys.stderr)
        return 1
    print(f"wrote {otf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
