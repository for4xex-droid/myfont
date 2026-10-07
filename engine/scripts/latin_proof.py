#!/usr/bin/env python3
"""管理文字列の組見本。OTF と TTF。黄金にはしない。"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.latin.compile import build_style
from engine.latin.proof import render_contact
from engine.latin.sheet import STYLES

_SIZES = (24, 48, 96, 300)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HOHOH などの組見本を OTF と TTF で描く"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "proofs" / "latin",
    )
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    built = {style: build_style(style) for style in STYLES}
    for kind in ("otf", "ttf"):
        fonts = {style: built[style][kind] for style in STYLES}
        path = out / f"text_{kind}.png"
        render_contact(fonts, _SIZES).save(path)
        print(path)


if __name__ == "__main__":
    main()
