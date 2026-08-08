"""B. GlyphWiki KAGE ダンプ取得・パース・部品参照統計（P4a 前提検証）。"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from kanji_lists import JOYO

from kage_parser import (
    STROKE_TYPE_NAMES,
    DumpEntry,
    flatten_glyph,
    is_alias,
    load_dump_index,
    parse_kage_data,
    resolve_alias_chain,
    sample_curve_points,
)

ROOT = Path(__file__).resolve().parent
DUMP = ROOT / "data" / "dump_newest_only.txt"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

# 画数の少ない字・多い字・囲み字・へんつくり字を混ぜたサンプル30字
SAMPLE_CHARS = list(
    "一二三十木人本大山口"  # 画数少
    "国囲園図回"  # 囲み
    "海詩村時話"  # へんつくり
    "永永"  # 可視化対象（重複除去後に永）
    "職議論鬱漢"  # 画数多
    "雨電食鳥"
)
# 重複除去しつつ順序維持
_seen = set()
SAMPLE_CHARS = [c for c in SAMPLE_CHARS if not (c in _seen or _seen.add(c))][:30]
# 永・国を確実に含める
for must in ("永", "国"):
    if must not in SAMPLE_CHARS:
        SAMPLE_CHARS.append(must)


def unicode_name(ch: str) -> str:
    return f"u{ord(ch):x}"


def count_parser_loc() -> Dict[str, int]:
    """パーサ実装の実測行数（空行・コメント除外）。"""
    import ast

    path = ROOT / "kage_parser.py"
    text = path.read_text(encoding="utf-8")
    total = len(text.splitlines())
    nonempty = sum(1 for line in text.splitlines() if line.strip())
    code = sum(
        1
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    tree = ast.parse(text)
    func_loc = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            end = node.end_lineno or node.lineno
            func_loc[node.name] = end - node.lineno + 1
    dump_funcs = ["parse_dump_line", "iter_dump", "load_dump_index"]
    stroke_funcs = ["parse_kage_data", "is_alias", "resolve_alias_chain"]
    flatten_funcs = ["flatten_glyph", "_compose_box", "_map_point", "_coords_to_points"]
    return {
        "file_total_lines": total,
        "file_nonempty_lines": nonempty,
        "file_code_lines": code,
        "dump_parse_funcs_loc": sum(func_loc.get(n, 0) for n in dump_funcs),
        "stroke_parse_funcs_loc": sum(func_loc.get(n, 0) for n in stroke_funcs),
        "flatten_funcs_loc": sum(func_loc.get(n, 0) for n in flatten_funcs),
        "func_loc": func_loc,
    }


def analyze_surface(entry: DumpEntry) -> Dict:
    strokes = parse_kage_data(entry.data)
    types = Counter(s.stroke_type for s in strokes)
    return {
        "name": entry.name,
        "related": entry.related,
        "n_strokes_surface": len(strokes),
        "type_counts": {STROKE_TYPE_NAMES.get(k, str(k)): v for k, v in types.items()},
        "has_ref99": any(s.stroke_type == 99 for s in strokes),
        "is_alias": is_alias(strokes),
        "ref_names": [s.ref_name for s in strokes if s.stroke_type == 99],
        "raw_preview": entry.data[:200],
    }


def write_skeleton_svg(
    char: str,
    flat_strokes,
    path: Path,
    *,
    title: str,
) -> None:
    """KAGE 200空間 → SVG 可視化（Y下向きのまま、prototype対照用に注記）。"""
    scale = 3.0
    pad = 20
    w = 200 * scale + pad * 2
    h = 200 * scale + pad * 2
    colors = {
        1: "#1a1a1a",
        2: "#0b5fff",
        3: "#c45c00",
        4: "#7a3db8",
        6: "#0a7a4a",
        7: "#b00020",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
        f"<title>{title}</title>",
        f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" fill="#f7f3ea"/>',
        f'<rect x="{pad}" y="{pad}" width="{200*scale}" height="{200*scale}" fill="none" stroke="#ccc" stroke-width="1"/>',
        f'<text x="{pad}" y="{pad-6}" font-family="Hiragino Mincho ProN,serif" font-size="14">{title}</text>',
    ]
    for i, s in enumerate(flat_strokes):
        pts = sample_curve_points(s.points, n=16)
        if len(pts) < 2:
            continue
        d = "M " + " L ".join(f"{pad + x*scale:.2f},{pad + y*scale:.2f}" for x, y in pts)
        col = colors.get(s.stroke_type, "#333")
        parts.append(
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linecap="round" data-i="{i}" data-type="{s.stroke_type}" data-start="{s.start_tag}" data-end="{s.end_tag}"/>'
        )
        # 端点マーク
        x0, y0 = pts[0]
        x1, y1 = pts[-1]
        parts.append(
            f'<circle cx="{pad + x0*scale:.2f}" cy="{pad + y0*scale:.2f}" r="3" fill="#222"/>'
        )
        parts.append(
            f'<circle cx="{pad + x1*scale:.2f}" cy="{pad + y1*scale:.2f}" r="3" fill="#888"/>'
        )
    # 凡例
    legend_y = pad + 200 * scale + 14
    parts.append(
        f'<text x="{pad}" y="{legend_y}" font-size="11" font-family="sans-serif">'
        f"1=straight 2=curve 3=bend 4=otsu 6=complex 7=vsweep | KAGE Y-down 200sq</text>"
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> None:
    t0 = time.time()
    assert DUMP.exists(), f"dump missing: {DUMP}"
    print(f"loading index from {DUMP} ...")
    index = load_dump_index(DUMP)
    load_sec = time.time() - t0
    print(f"index size={len(index)} in {load_sec:.2f}s")

    # 常用漢字カバー率＋エイリアス解決後の部品参照率
    joyo = list(JOYO)
    covered = 0
    missing_names: List[str] = []
    alias_only = 0
    surface_ref99 = 0
    post_alias_still_has_ref99 = 0
    post_alias_pure_strokes = 0  # 解決後に99なし（素筆画のみ）
    flatten_depth_all: List[int] = []
    flatten_fail = 0
    t_flat = time.time()
    for ch in joyo:
        name = unicode_name(ch)
        lookup = name if name in index else (f"{name}-j" if f"{name}-j" in index else None)
        if lookup is None:
            missing_names.append(name)
            continue
        covered += 1
        strokes = parse_kage_data(index[lookup].data)
        if is_alias(strokes):
            alias_only += 1
        if any(s.stroke_type == 99 for s in strokes):
            surface_ref99 += 1
        final, chain, final_strokes = resolve_alias_chain(lookup, index)
        if any(s.stroke_type == 99 for s in final_strokes):
            post_alias_still_has_ref99 += 1
        else:
            post_alias_pure_strokes += 1
        flat, max_depth, missing = flatten_glyph(lookup, index)
        flatten_depth_all.append(max_depth)
        if missing or not flat:
            flatten_fail += 1
    flat_sec = time.time() - t_flat

    # サンプル30字の深掘り
    sample_rows = []
    type_tag_pairs = Counter()
    depths = []
    need_component_resolve = 0
    for ch in SAMPLE_CHARS:
        name = unicode_name(ch)
        entry = index.get(name) or index.get(f"{name}-j")
        if entry is None:
            sample_rows.append({"char": ch, "name": name, "error": "missing"})
            continue
        surface = analyze_surface(entry)
        final, chain, _ = resolve_alias_chain(name if name in index else entry.name, index)
        flat, max_depth, missing = flatten_glyph(name if name in index else entry.name, index)
        # 展開後の type×tag
        for s in flat:
            type_tag_pairs[(s.stroke_type, s.start_tag, s.end_tag)] += 1
        # 表面または展開で部品が必要か
        needs_resolve = surface["has_ref99"] or len(chain) > 1
        if needs_resolve:
            need_component_resolve += 1
        depths.append(max_depth)
        row = {
            "char": ch,
            "name": name,
            "alias_chain": chain,
            "final_name": final,
            "surface": surface,
            "flattened_stroke_count": len(flat),
            "max_recursion_depth": max_depth,
            "missing_refs": missing,
            "needs_component_resolve": needs_resolve,
        }
        sample_rows.append(row)

        # 永・国のSVG
        if ch in ("永", "国"):
            write_skeleton_svg(
                ch,
                flat,
                OUT / f"kage_skeleton_{name}_{ch}.svg",
                title=f"{ch} ({name}) flattened KAGE skeleton",
            )
            # 写像可能性メモ用に内部風 JSON
            mapped = []
            for s in flat:
                mapped.append(
                    {
                        "kage_type": s.stroke_type,
                        "type_name": STROKE_TYPE_NAMES.get(s.stroke_type, "?"),
                        "start_tag": s.start_tag,
                        "end_tag": s.end_tag,
                        "points": [{"x": x, "y": y} for x, y in s.points],
                        "source": s.source_path,
                    }
                )
            (OUT / f"kage_flat_{name}.json").write_text(
                json.dumps(mapped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    loc = count_parser_loc()
    n_sample = len([r for r in sample_rows if "error" not in r])
    report = {
        "dump_path": str(DUMP),
        "dump_size_bytes": DUMP.stat().st_size,
        "index_entries": len(index),
        "load_seconds": round(load_sec, 3),
        "joyo_total": len(joyo),
        "joyo_covered": covered,
        "joyo_coverage_ratio": round(covered / len(joyo), 4),
        "joyo_missing_count": len(missing_names),
        "joyo_missing_sample": missing_names[:20],
        "joyo_surface_alias_or_redirect": alias_only,
        "joyo_surface_has_ref99": surface_ref99,
        "joyo_surface_ref99_ratio": round(surface_ref99 / max(covered, 1), 4),
        "joyo_post_alias_still_has_ref99": post_alias_still_has_ref99,
        "joyo_post_alias_still_has_ref99_ratio": round(
            post_alias_still_has_ref99 / max(covered, 1), 4
        ),
        "joyo_post_alias_pure_primitive_strokes": post_alias_pure_strokes,
        "joyo_flatten_fail_or_empty": flatten_fail,
        "joyo_flatten_seconds": round(flat_sec, 3),
        "joyo_max_recursion_depth_max": max(flatten_depth_all) if flatten_depth_all else None,
        "joyo_max_recursion_depth_mean": (
            round(sum(flatten_depth_all) / len(flatten_depth_all), 3) if flatten_depth_all else None
        ),
        "joyo_max_recursion_depth_p95": (
            sorted(flatten_depth_all)[int(len(flatten_depth_all) * 0.95)]
            if flatten_depth_all
            else None
        ),
        "sample_chars": SAMPLE_CHARS,
        "sample_count": n_sample,
        "sample_need_component_resolve": need_component_resolve,
        "sample_need_component_resolve_ratio": round(
            need_component_resolve / max(n_sample, 1), 4
        ),
        "sample_max_recursion_depth_values": depths,
        "sample_max_recursion_depth_max": max(depths) if depths else None,
        "sample_max_recursion_depth_mean": round(sum(depths) / len(depths), 3) if depths else None,
        "parser_loc": loc,
        "dozens_of_lines_claim": {
            "plan_claim": "GlyphWiki ダンプのパース（name|related|data の | 区切り）は数十行で書ける",
            "dump_parse_funcs_loc": loc["dump_parse_funcs_loc"],
            "stroke_parse_funcs_loc": loc["stroke_parse_funcs_loc"],
            "full_parser_file_code_lines": loc["file_code_lines"],
            "verdict_on_dump_line_parse": (
                "前提成立"
                if loc["dump_parse_funcs_loc"] <= 60
                else "条件付き（数十行超）"
            ),
            "note": "「数十行」は dump 行分解に妥当。部品展開・座標写像を含めると百行超になり得る",
        },
        "svg_outputs": [
            str(OUT / "kage_skeleton_u6c38_永.svg"),
            str(OUT / "kage_skeleton_u56fd_国.svg"),
        ],
        "sample_rows": sample_rows,
        "type_tag_pair_counts": {
            f"t{a}_s{b}_e{c}": n for (a, b, c), n in type_tag_pairs.most_common()
        },
    }
    (OUT / "verify_b_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # コンソール要約
    summary = {k: report[k] for k in report if k not in ("sample_rows", "type_tag_pair_counts")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
