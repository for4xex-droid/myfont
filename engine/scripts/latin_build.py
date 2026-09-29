#!/usr/bin/env python3
"""内部用にパイロット6字を OTF と TTF にする。引き渡し用ではない。"""

from __future__ import annotations

import argparse
import json

from engine.latin.compile import BUILD_DIR, build_style
from engine.latin.measure import measure_otf


def main() -> None:
    parser = argparse.ArgumentParser(description="ラテン書体の内部ビルド（version 0.001）")
    parser.add_argument("--style", action="append", dest="styles")
    args = parser.parse_args()
    styles = args.styles or ["modern", "classic", "chic", "pop"]
    report = {}
    for name in styles:
        paths = build_style(name)
        metrics = measure_otf(paths["otf"])
        report[name] = {"otf": str(paths["otf"]), "ttf": str(paths["ttf"]), **metrics}
        print(name, paths["otf"])
    out = BUILD_DIR / "separation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
