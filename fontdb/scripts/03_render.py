#!/usr/bin/env python3
"""T3: 代表字ラスタ化（十を全 face で PNG 出力）。"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontdb.paths import CORPUS_YAML, PACKAGE_ROOT, RENDERS_DIR
from fontdb.render.freetype_raster import (
    load_face,
    place_on_em_canvas,
    render_glyph_gray,
)


def main() -> int:
    with open(CORPUS_YAML, encoding="utf-8") as f:
        corpus = yaml.safe_load(f)
    families = [x for x in corpus["families"] if x.get("acquired")]
    if not families:
        print("no acquired fonts", file=sys.stderr)
        return 1
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    for fam in families:
        path = PACKAGE_ROOT / fam["path_rel"]
        face = load_face(str(path))
        gray, meta = render_glyph_gray(face, "十", hinting=False)
        canvas = place_on_em_canvas(gray, meta)
        out = RENDERS_DIR / f"{fam['family_id']}_十_nohint.png"
        Image.fromarray(canvas, mode="L").save(out)
        gray_h, meta_h = render_glyph_gray(face, "十", hinting=True)
        canvas_h = place_on_em_canvas(gray_h, meta_h)
        out_h = RENDERS_DIR / f"{fam['family_id']}_十_hint.png"
        Image.fromarray(canvas_h, mode="L").save(out_h)
        print("wrote", out.name, out_h.name, "diff=", (canvas != canvas_h).any())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
