#!/usr/bin/env python3
"""仮名レビュー用の決定的 PNG レンダ（レビューループ A）。

S4 make_proofs には触らない。OTF は非コミット前提で SHA を meta に記録する。

例:
  python scripts/kana_render.py --glyph shi
  python scripts/kana_render.py --glyph to --text しいと --tag trio
  python scripts/kana_render.py --text しいとつ --tag quad   # 複数字まとめ（board/）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # engine/
SRC = ROOT / "src"
REPO = ROOT.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 固定レンダ契約（変えるときは tag / meta.version を上げる）
RENDER_VERSION = "kana_render_v1"
EM_PX = 256
PAD_X = 24
PAD_Y = 24
BASELINE_FRAC = 0.85
COORDINATE_SPACE = "svg_y_down_legacy"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_otf(params: str) -> Path:
    return ROOT / "output" / "regen" / params / f"MyMincho-{params}-Regular.otf"


def render_text_png(
    font: Path,
    text: str,
    out_png: Path,
    *,
    em_px: int = EM_PX,
    pad_x: int = PAD_X,
    pad_y: int = PAD_Y,
    baseline_frac: float = BASELINE_FRAC,
) -> dict:
    """freetype cmap 直描画（hinting off）。仮名単字・単純列用。戻り値に png_sha256。"""
    import io

    import freetype
    import numpy as np
    from PIL import Image

    face = freetype.Face(str(font))
    face.set_pixel_sizes(em_px, em_px)
    # 事前に幅を見積もる
    advances: list[float] = []
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_NO_HINTING)
        advances.append(face.glyph.advance.x / 64.0)
    total_adv = sum(advances) if advances else float(em_px)
    height = em_px + pad_y * 2
    width = max(int(total_adv) + pad_x * 2, em_px + pad_x * 2)
    canvas = np.zeros((height, width), dtype=np.uint8)
    pen_x = float(pad_x)
    baseline = int(em_px * baseline_frac) + pad_y

    for ch in text:
        face.load_char(
            ch, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER
        )
        glyph = face.glyph
        bitmap = glyph.bitmap
        w, h, pitch = bitmap.width, bitmap.rows, bitmap.pitch
        if w > 0 and h > 0:
            raw = bytes(bitmap.buffer)
            arr = np.zeros((h, w), dtype=np.uint8)
            for row in range(h):
                start = row * pitch
                arr[row, :] = np.frombuffer(raw[start : start + w], dtype=np.uint8)
            x0 = int(pen_x + glyph.bitmap_left)
            y0 = int(baseline - glyph.bitmap_top)
            x1, y1 = x0 + w, y0 + h
            cx0, cy0 = max(0, x0), max(0, y0)
            cx1, cy1 = min(width, x1), min(height, y1)
            if cx0 < cx1 and cy0 < cy1:
                gx0, gy0 = cx0 - x0, cy0 - y0
                roi = canvas[cy0:cy1, cx0:cx1]
                src = arr[gy0 : gy0 + (cy1 - cy0), gx0 : gx0 + (cx1 - cx0)]
                canvas[cy0:cy1, cx0:cx1] = np.maximum(roi, src)
        pen_x += glyph.advance.x / 64.0

    out_png.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    Image.fromarray(255 - canvas, mode="L").save(buf, format="PNG")
    png_bytes = buf.getvalue()
    out_png.write_bytes(png_bytes)
    return {
        "ok": True,
        "png": str(out_png),
        "png_sha256": _sha256_bytes(png_bytes),
        "width": width,
        "height": height,
        "backend": "freetype_cmap",
        "em_px": em_px,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "baseline_frac": baseline_frac,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic kana review render")
    ap.add_argument(
        "--glyph",
        default=None,
        help="glyph_id e.g. shi（省略時は --text 必須・出力は board/）",
    )
    ap.add_argument("--params", default="product_r1")
    ap.add_argument(
        "--font",
        type=Path,
        default=None,
        help="OTF path (default: engine/output/regen/<params>/...)",
    )
    ap.add_argument(
        "--text",
        default=None,
        help="描画文字列（省略時は glyph の1字。複数字まとめ可）",
    )
    ap.add_argument("--tag", default="single", help="output tag name")
    ap.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "proofs" / "out" / "kana",
        help="output root (default: proofs/out/kana)",
    )
    ap.add_argument(
        "--compare-golden",
        action="store_true",
        help="SHA256 compare against proofs/golden/kana_<glyph|board>/<tag>.png",
    )
    args = ap.parse_args(argv)

    from engine.kana import KANA_GLYPH_META, kana_characters, skeletons_dir
    from engine.params import PARAM_SETS

    if args.params not in PARAM_SETS:
        print(f"error: unknown params {args.params}", file=sys.stderr)
        return 2

    chars = kana_characters()
    board_mode = args.glyph is None
    if board_mode:
        if not args.text:
            print("error: --glyph か --text のどちらかが必要", file=sys.stderr)
            return 2
        text = args.text
        glyph_id = "board"
        yaml_path = None
    else:
        if args.glyph not in chars:
            print(f"error: unknown kana glyph {args.glyph}", file=sys.stderr)
            return 2
        glyph_id = args.glyph
        meta_g = KANA_GLYPH_META[glyph_id]
        text = args.text if args.text is not None else str(meta_g["char"])
        yaml_path = skeletons_dir() / f"{glyph_id}.yaml"
        if not yaml_path.is_file():
            cands = list(skeletons_dir().glob("*.yaml"))
            yaml_path = next(
                (p for p in cands if load_match(p, glyph_id)), yaml_path
            )

    font = args.font or _default_otf(args.params)
    if not font.is_file():
        hint = args.glyph or "shi i to tsu"
        print(
            f"error: OTF not found: {font}\n"
            f"  run: python scripts/regen.py --params {args.params} --glyphs {hint}",
            file=sys.stderr,
        )
        return 2

    out_dir = args.out_root / glyph_id
    out_png = out_dir / f"{args.tag}.png"
    out_meta = out_dir / f"{args.tag}.meta.json"

    try:
        rendered = render_text_png(font, text, out_png)
    except ImportError as e:
        print(f"error: deps missing: {e}", file=sys.stderr)
        return 2

    params_yaml = ROOT / "params" / f"{args.params}.yaml"
    meta = {
        "render_version": RENDER_VERSION,
        "glyph_id": glyph_id,
        "text": text,
        "tag": args.tag,
        "params": args.params,
        "coordinate_space": COORDINATE_SPACE,
        "otf_path": str(font),
        "otf_sha256": _sha256_file(font),
        "skeleton_yaml": str(yaml_path) if yaml_path and yaml_path.is_file() else None,
        "skeleton_yaml_sha256": (
            _sha256_file(yaml_path) if yaml_path and yaml_path.is_file() else None
        ),
        "params_yaml_sha256": (
            _sha256_file(params_yaml) if params_yaml.is_file() else None
        ),
        "png": str(out_png),
        "png_sha256": rendered["png_sha256"],
        "width": rendered["width"],
        "height": rendered["height"],
        "em_px": rendered["em_px"],
        "pad_x": rendered["pad_x"],
        "pad_y": rendered["pad_y"],
        "baseline_frac": rendered["baseline_frac"],
        "backend": rendered["backend"],
    }
    out_meta.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"png={out_png}")
    print(f"meta={out_meta}")
    print(f"png_sha256={meta['png_sha256'][:16]}… otf_sha256={meta['otf_sha256'][:16]}…")

    if args.compare_golden:
        golden = REPO / "proofs" / "golden" / f"kana_{glyph_id}" / f"{args.tag}.png"
        if not golden.is_file():
            print(f"golden: missing {golden}")
            return 1
        same = _sha256_file(golden) == meta["png_sha256"]
        print(f"golden: {'MATCH' if same else 'DIFF'} ({golden})")
        return 0 if same else 1
    return 0


def load_match(path: Path, glyph_id: str) -> bool:
    from engine.kana import load_kana_skeleton

    try:
        gid, _, _ = load_kana_skeleton(path)
    except ValueError:
        return False
    return gid == glyph_id


if __name__ == "__main__":
    raise SystemExit(main())
