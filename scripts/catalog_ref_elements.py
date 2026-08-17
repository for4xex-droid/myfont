#!/usr/bin/env python3
"""参照から多面の要素家族をカタログする。輪郭点は持たない。正本は書かない。

面: 軸画 / 箱と穴 / 永字八法 / 斜画 / 字面と余白 / うろこ家族

例:
  engine/.venv/bin/python scripts/catalog_ref_elements.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_ref_elements import extract_char
from reproduce_ref import INK, OUT_DEFAULT, REF_DEFAULT, assert_throwaway, pack_bbox, render_em

CATALOG_CHARS = "十二三口日田中永木人本入八"

FACETS = {
    "十": ["axis", "cross"],
    "二": ["axis"],
    "三": ["axis"],
    "口": ["box"],
    "日": ["box"],
    "田": ["box"],
    "中": ["box", "cross"],
    "永": ["eight"],
    "木": ["tree", "diag"],
    "本": ["tree", "diag"],
    "人": ["diag"],
    "入": ["diag"],
    "八": ["diag"],
}


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[len(s) // 2]


def _span(xs: list[float]) -> list[float] | None:
    if not xs:
        return None
    return [round(min(xs), 4), round(max(xs), 4)]


def library_from(rows: list[dict]) -> dict:
    contrasts = [r["contrast_v_over_h"] for r in rows if r["contrast_v_over_h"]]
    h_em = [r["h_thickness_em"] for r in rows if r["h_thickness_em"]]
    v_em = [r["v_thickness_em"] for r in rows if r["v_thickness_em"]]
    face_w = [r["face_em"][0] for r in rows]
    face_h = [r["face_em"][1] for r in rows]
    lsb = [r["lsb_em"] for r in rows]
    ink = [r["ink_em"] for r in rows]
    bar = []
    box = []
    for r in rows:
        for t in r["terminals"]:
            u = t.get("uroko")
            if not u:
                continue
            if t["role"] == "bar_uroko" and u["height_over_h"] < 6.0:
                bar.append(u)
            elif t["role"] == "box_uroko":
                box.append(u)
    roles = Counter(role for r in rows for role in r["roles"])
    return {
        "n_glyphs": len(rows),
        "contrast_v_over_h": {
            "median": round(_median(contrasts), 3) if contrasts else None,
            "span": _span(contrasts),
        },
        "h_thickness_em": {
            "median": round(_median(h_em), 4) if h_em else None,
            "span": _span(h_em),
        },
        "v_thickness_em": {
            "median": round(_median(v_em), 4) if v_em else None,
            "span": _span(v_em),
        },
        "face_em": {
            "width_median": round(_median(face_w), 4) if face_w else None,
            "height_median": round(_median(face_h), 4) if face_h else None,
        },
        "lsb_em_median": round(_median(lsb), 4) if lsb else None,
        "ink_em_median": round(_median(ink), 4) if ink else None,
        "bar_uroko": {
            "n": len(bar),
            "width_over_h": _span([u["width_over_h"] for u in bar]),
            "height_over_h": _span([u["height_over_h"] for u in bar]),
            "width_em": _span([u["width_em"] for u in bar]),
            "height_em": _span([u["height_em"] for u in bar]),
        },
        "box_uroko": {
            "n": len(box),
            "width_over_h": _span([u["width_over_h"] for u in box]),
            "height_over_h": _span([u["height_over_h"] for u in box]),
            "width_em": _span([u["width_em"] for u in box]),
            "height_em": _span([u["height_em"] for u in box]),
        },
        "role_counts": dict(roles),
        "counters": {r["char"]: r["n_counter"] for r in rows if r["n_counter"]},
    }


def slim_row(row: dict) -> dict:
    """カタログにはスカラーだけ。ステム座標も残差点も持たない。"""
    return {
        "char": row["char"],
        "unicode": row["unicode"],
        "facets": FACETS.get(row["char"], []),
        "h_thickness_em": row["h_thickness_em"],
        "v_thickness_em": row["v_thickness_em"],
        "contrast_v_over_h": row["contrast_v_over_h"],
        "face_em": row["face_em"],
        "lsb_em": row["lsb_em"],
        "rsb_em": row["rsb_em"],
        "ink_em": row["ink_em"],
        "n_stem": len(row["stems"]),
        "n_counter": row["n_counter"],
        "n_outer": row["n_outer"],
        "roles": row["roles"],
        "residual_frac": row["residual_frac"],
        "lossless": row["lossless"],
        "uroko": [t["uroko"] | {"role": t["role"]} for t in row["terminals"] if t.get("uroko")],
        "counters": row["counters"],
    }


def write_md(rows: list[dict], lib: dict, dest: Path) -> None:
    lines = [
        "# 参照要素カタログ",
        "",
        "輪郭点は持たない。計測スカラーと役割だけ。正本は書いていない。",
        "",
        "## 家族",
        "",
        f"- contrast 中央 {lib['contrast_v_over_h']['median']} 幅 {lib['contrast_v_over_h']['span']}",
        f"- 横太さ {lib['h_thickness_em']['median']} em  縦太さ {lib['v_thickness_em']['median']} em",
        f"- 字面 幅 {lib['face_em']['width_median']} / 高さ {lib['face_em']['height_median']} em",
        f"- 棒うろこ n={lib['bar_uroko']['n']}  幅/横 {lib['bar_uroko']['width_over_h']}  高/横 {lib['bar_uroko']['height_over_h']}",
        f"- 箱うろこ n={lib['box_uroko']['n']}  幅/横 {lib['box_uroko']['width_over_h']}  高/横 {lib['box_uroko']['height_over_h']}",
        f"- 穴 {lib['counters']}",
        "",
        "## 字",
        "",
        "| 字 | 面 | 横em | 縦em | c | 穴 | residual | roles |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['char']} | {','.join(r['facets']) or '—'} | {r['h_thickness_em'] or '—'} | "
            f"{r['v_thickness_em'] or '—'} | {r['contrast_v_over_h'] or '—'} | {r['n_counter']} | "
            f"{r['residual_frac']} | {','.join(r['roles']) or '—'} |"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sheet(pairs: list[tuple[str, np.ndarray, str]], dest: Path) -> None:
    from PIL import Image, ImageDraw

    cell = 160
    pad = 8
    label_h = 36
    cols = 5
    rows_n = (len(pairs) + cols - 1) // cols
    page = Image.new(
        "RGB",
        (cols * (cell + pad) + pad, rows_n * (cell + label_h + pad) + pad),
        (255, 255, 255),
    )
    draw = ImageDraw.Draw(page)
    for i, (ch, im, note) in enumerate(pairs):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + label_h + pad)
        page.paste(Image.fromarray((~im).astype(np.uint8) * 255).convert("RGB"), (x, y))
        draw.text((x, y + cell + 2), f"{ch} {note}", fill=(0, 0, 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.save(dest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Catalog shared element families from a reference")
    ap.add_argument("--ref", type=Path, default=REF_DEFAULT)
    ap.add_argument("--chars", default=CATALOG_CHARS)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if not args.ref.is_file():
        print(f"error: missing {args.ref}", file=sys.stderr)
        return 2
    assert_throwaway(args.out / "_scratch")
    raw = [extract_char(args.ref, ch) for ch in args.chars]
    rows = [slim_row(r) for r in raw]
    lib = library_from(raw)
    payload = {
        "ref": str(args.ref),
        "shipping_ufo_written": False,
        "method": "multi-facet-scalars",
        "library": lib,
        "glyphs": rows,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "catalog.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_md(rows, lib, args.out / "catalog.md")
    pairs = []
    for r in rows:
        canvas = render_em(args.ref, r["char"])
        note = f"c={r['contrast_v_over_h'] or '—'} hole={r['n_counter']}"
        pairs.append((r["char"], pack_bbox(canvas, size=160), note))
    png = args.out / "catalog.png"
    sheet(pairs, png)
    print(
        f"glyphs={lib['n_glyphs']} contrast={lib['contrast_v_over_h']} "
        f"bar_uroko={lib['bar_uroko']['n']} box_uroko={lib['box_uroko']['n']} "
        f"holes={lib['counters']}"
    )
    print(f"wrote {json_path} {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
