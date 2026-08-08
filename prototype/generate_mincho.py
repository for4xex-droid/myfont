#!/usr/bin/env python3
"""
明朝体ディテール自動生成プロトタイプ。

骨格(中心線)＋端点タグから、うろこ・打ち込み・はね・はらい・テーパーを
パラメータ駆動でアウトライン化し、SVG として出力する。
標準ライブラリのみ。
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from typing import List, Sequence, Tuple

from params import PARAM_SETS, MinchoParams
from skeletons import CHAR_LABELS, CHARACTERS
from strokes import build_stroke, strokes_to_svg_paths


UPM = 1000
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def render_glyph(strokes, params: MinchoParams) -> Tuple[str, List[List[Vec2]]]:
    """全ストロークをアウトライン化し、SVG path d とポリゴン一覧を返す。"""
    all_parts: List[List[Vec2]] = []
    for s in strokes:
        parts = build_stroke(s, params)
        all_parts.extend(parts)
    d = strokes_to_svg_paths(all_parts)
    return d, all_parts


def make_svg(path_d: str, title: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {UPM} {UPM}"
     width="{UPM}" height="{UPM}">
  <title>{title}</title>
  <!-- ガイド（薄い枠） -->
  <rect x="0" y="0" width="{UPM}" height="{UPM}" fill="none" stroke="#ddd" stroke-width="1"/>
  <path d="{path_d}" fill="#000000" fill-rule="nonzero" stroke="none"/>
</svg>
"""


def validate_svg(path: str) -> List[str]:
    """SVG の構文・パス閉じを簡易検証。問題があればメッセージを返す。"""
    issues: List[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return [f"XML構文エラー: {e}"]

    root = tree.getroot()
    # namespace 対応
    tag = root.tag
    if not tag.endswith("svg"):
        issues.append(f"ルートが svg ではない: {tag}")

    vb = root.get("viewBox", "")
    if vb.strip() != "0 0 1000 1000":
        issues.append(f"viewBox が期待と異なる: {vb!r}")

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    paths = list(root.iter(f"{ns}path"))
    if not paths:
        issues.append("path 要素が無い")
        return issues

    for i, pe in enumerate(paths):
        d = pe.get("d", "")
        if not d.strip():
            issues.append(f"path[{i}] が空")
            continue
        # サブパスが Z で閉じているか
        # 簡易: 'Z' または 'z' の数と M の数を比較
        m_count = d.count("M") + d.count("m")
        z_count = d.count("Z") + d.count("z")
        if z_count < m_count:
            issues.append(
                f"path[{i}] 閉じが不足: M={m_count}, Z={z_count}"
            )
        # 座標トークンが数値として読めるかざっくり確認
        tokens = d.replace(",", " ").split()
        expect_num = False
        for tok in tokens:
            if tok in ("M", "L", "Z", "m", "l", "z", "H", "V", "C", "Q", "S", "T", "A"):
                expect_num = tok.upper() in ("M", "L", "H", "V", "C", "Q", "S", "T", "A")
                continue
            try:
                float(tok)
            except ValueError:
                issues.append(f"path[{i}] 不正トークン: {tok!r}")
                break
    return issues


def generate_all(param_names: Sequence[str] | None = None) -> List[str]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    names = list(param_names) if param_names else list(PARAM_SETS.keys())
    written: List[str] = []

    for pname in names:
        params = PARAM_SETS[pname]
        for ckey, strokes in CHARACTERS.items():
            label = CHAR_LABELS[ckey]
            d, parts = render_glyph(strokes, params)
            fname = f"{ckey}_{label}_{pname}.svg"
            out_path = os.path.join(OUTPUT_DIR, fname)
            title = f"{label} ({ckey}) / params={pname}"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(make_svg(d, title))
            written.append(out_path)

            issues = validate_svg(out_path)
            status = "OK" if not issues else "NG: " + "; ".join(issues)
            n_poly = len(parts)
            n_pts = sum(len(p) for p in parts)
            print(f"  [{status}] {out_path}  polygons={n_poly} points={n_pts}")

    return written


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="明朝体ディテール生成プロトタイプ")
    parser.add_argument(
        "--params",
        nargs="*",
        default=None,
        help="パラメータセット名 (classic modern)",
    )
    args = parser.parse_args(argv)

    print("=== Mincho detail generation prototype ===")
    print(f"output: {OUTPUT_DIR}")
    written = generate_all(args.params)
    print(f"generated: {len(written)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
