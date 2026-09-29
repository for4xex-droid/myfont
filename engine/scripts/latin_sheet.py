#!/usr/bin/env python3
"""パイロット比較シートを書く。内部確認用。"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.latin.sheet import render_pilot_sheet


def main() -> None:
    parser = argparse.ArgumentParser(description="H O B V S 0 × 4様式の比較シート")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "proofs" / "latin" / "pilot_sheet.png",
    )
    args = parser.parse_args()
    print(render_pilot_sheet(args.output))


if __name__ == "__main__":
    main()
