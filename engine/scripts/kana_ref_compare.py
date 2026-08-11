#!/usr/bin/env python3
"""参照明朝4書体と自作OTFの仮名をラスタ比較（クリーンルーム: スカラー計測のみ）。

- 参照: fontdb/data/fonts/ の伝統明朝クラスタ（源ノ・IPAex・しっぽり・Zen Old）
- 出力: スカラー表＋横並び比較PNG
- 座標トレース禁止（掟9）。ここで出すのは帯合わせ用スカラーだけ。

例:
  python scripts/kana_ref_compare.py つ
  python scripts/kana_ref_compare.py つ --out /tmp/tsu_compare.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # engine/
REPO = ROOT.parent

REFERENCE_FONTS: dict[str, Path] = {
    "source_han": REPO / "fontdb/data/fonts/source_han_serif_jp-Regular.otf",
    "ipaex": REPO / "fontdb/data/fonts/ipaex_mincho-Regular.ttf",
    "shippori": REPO / "fontdb/data/fonts/shippori_mincho-Regular.ttf",
    "zen_old": REPO / "fontdb/data/fonts/zen_old_mincho-Regular.ttf",
}
EM_PX = 256
INK_THRESHOLD = 64


def render_char(font_path: Path, char: str, em_px: int = EM_PX):
    import freetype
    import numpy as np

    face = freetype.Face(str(font_path))
    face.set_pixel_sizes(em_px, em_px)
    face.load_char(char, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    arr = np.zeros((bm.rows, bm.width), dtype=np.uint8)
    buf = bytes(bm.buffer)
    for r in range(bm.rows):
        arr[r, :] = np.frombuffer(
            buf[r * bm.pitch : r * bm.pitch + bm.width], dtype=np.uint8
        )
    return arr


def measure_scalars(arr) -> dict[str, float] | None:
    """帯合わせ用の粗いスカラー（bbox正規化）。"""
    import numpy as np

    ink = arr > INK_THRESHOLD
    ys, xs = np.where(ink)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    sub = ink[y0 : y1 + 1, x0 : x1 + 1]
    band = max(1, h // 10)
    _, txs = np.where(sub[:band, :])
    _, bxs = np.where(sub[h - band :, :])
    cy, cx = np.where(sub)
    return {
        "aspect_w_over_h": round(w / h, 3),
        "top_ink_left_frac": round(float(txs.min()) / w, 3) if len(txs) else -1.0,
        "top_ink_right_frac": round(float(txs.max()) / w, 3) if len(txs) else -1.0,
        "bottom_cx_frac": round(float(bxs.mean()) / w, 3) if len(bxs) else -1.0,
        "centroid_x_frac": round(float(cx.mean()) / w, 3),
        "centroid_y_frac": round(float(cy.mean()) / h, 3),
        "ink_density": round(float(sub.mean()), 3),
        "w_px": int(w),
        "h_px": int(h),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reference Mincho scalar comparison")
    ap.add_argument("char", help="e.g. つ")
    ap.add_argument(
        "--font",
        type=Path,
        default=ROOT / "output/regen/product_r1/MyMincho-product_r1-Regular.otf",
        help="our OTF (default: regen product_r1)",
    )
    ap.add_argument("--out", type=Path, default=None, help="comparison PNG path")
    args = ap.parse_args(argv)

    import numpy as np
    from PIL import Image

    fonts = dict(REFERENCE_FONTS)
    fonts["OURS"] = args.font
    missing = [n for n, p in fonts.items() if not p.is_file()]
    if missing:
        print(f"error: missing fonts: {missing}", file=sys.stderr)
        return 2

    cols = [
        "aspect_w_over_h",
        "top_ink_left_frac",
        "top_ink_right_frac",
        "bottom_cx_frac",
        "centroid_y_frac",
        "ink_density",
    ]
    header = f"{'font':12} " + " ".join(f"{c.split('_')[0]:>7}" for c in cols)
    print(f"char={args.char}")
    print(header)

    ref_values: dict[str, list[float]] = {c: [] for c in cols}
    tiles = []
    for name, fp in fonts.items():
        arr = render_char(fp, args.char)
        m = measure_scalars(arr)
        if m is None:
            print(f"{name:12} (no ink)")
            continue
        print(f"{name:12} " + " ".join(f"{m[c]:>7}" for c in cols))
        if name != "OURS":
            for c in cols:
                ref_values[c].append(m[c])
        tile = np.zeros((EM_PX + 40, EM_PX + 40), dtype=np.uint8)
        h, w = arr.shape
        oy, ox = (EM_PX + 40 - h) // 2, (EM_PX + 40 - w) // 2
        tile[oy : oy + h, ox : ox + w] = arr
        tiles.append(tile)

    # 参照帯（min/max）を印字（骨格YAML の gate / 目標帯設計に使う）
    print("reference band (min..max):")
    for c in cols:
        vs = ref_values[c]
        if vs:
            print(f"  {c}: {min(vs)} .. {max(vs)}")

    if args.out and tiles:
        h_max = max(t.shape[0] for t in tiles)
        w_sum = sum(t.shape[1] for t in tiles) + 10 * (len(tiles) - 1)
        page = np.zeros((h_max, w_sum), dtype=np.uint8)
        x = 0
        for t in tiles:
            page[: t.shape[0], x : x + t.shape[1]] = t
            x += t.shape[1] + 10
        args.out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(255 - page, mode="L").save(args.out)
        print(f"comparison: {args.out} (order: {', '.join(fonts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
