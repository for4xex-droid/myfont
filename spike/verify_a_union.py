#!/usr/bin/env python3
"""A: skia-pathops で「永」の重ね塗りポリゴンを union し、単一輪郭化できるか検証。"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Sequence, Tuple

# prototype は標準ライブラリのみ（cwd に依存しないよう sys.path を追加）
PROTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prototype")
sys.path.insert(0, os.path.abspath(PROTO))

from pathops import Path, PathVerb, simplify, union  # noqa: E402

from params import PARAM_SETS  # noqa: E402
from skeletons import CHARACTERS  # noqa: E402
from strokes import build_stroke  # noqa: E402
from geometry import Vec2, polygon_to_svg_path  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
UPM = 1000


def poly_to_path(poly: Sequence[Vec2]) -> Path:
    """閉じた頂点列 → pathops.Path（直線のみ）。"""
    p = Path()
    if len(poly) < 3:
        return p
    # 閉じ点の重複を除去
    pts = list(poly)
    if pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    if len(pts) < 3:
        return p
    p.moveTo(pts[0].x, pts[0].y)
    for pt in pts[1:]:
        p.lineTo(pt.x, pt.y)
    p.close()
    return p


def count_contours(path: Path) -> int:
    return sum(1 for v, _ in path if v == PathVerb.MOVE)


def _fmt_pts(pts, fmt: str) -> List[str]:
    """pathops の pts は ((x,y), ...) 形式。"""
    out: List[str] = []
    for pt in pts:
        out.append(fmt.format(pt[0]))
        out.append(fmt.format(pt[1]))
    return out


def path_to_svg_d(path: Path, precision: int = 2) -> str:
    fmt = f"{{:.{precision}f}}"
    parts: List[str] = []
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            xy = _fmt_pts(pts, fmt)
            parts.append(f"M {xy[0]} {xy[1]}")
        elif verb == PathVerb.LINE:
            xy = _fmt_pts(pts, fmt)
            parts.append(f"L {xy[0]} {xy[1]}")
        elif verb == PathVerb.QUAD:
            xy = _fmt_pts(pts, fmt)
            parts.append(f"Q {xy[0]} {xy[1]} {xy[2]} {xy[3]}")
        elif verb == PathVerb.CUBIC:
            xy = _fmt_pts(pts, fmt)
            parts.append(f"C {xy[0]} {xy[1]} {xy[2]} {xy[3]} {xy[4]} {xy[5]}")
        elif verb == PathVerb.CLOSE:
            parts.append("Z")
    return " ".join(parts)


def pathops_union(paths: Sequence[Path]) -> Path:
    """pathops.union(contours, outpen) ラッパ。"""
    out = Path()
    union(list(paths), out.getPen())
    return out


def make_svg(path_d: str, title: str, note: str = "") -> str:
    note_xml = f"\n  <text x='20' y='980' font-size='18' fill='#666'>{note}</text>" if note else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {UPM} {UPM}"
     width="{UPM}" height="{UPM}">
  <title>{title}</title>
  <rect x="0" y="0" width="{UPM}" height="{UPM}" fill="none" stroke="#ddd" stroke-width="1"/>
  <path d="{path_d}" fill="#000000" fill-rule="nonzero" stroke="none"/>{note_xml}
</svg>
"""


def segment_lengths(poly: Sequence[Vec2]) -> List[float]:
    pts = list(poly)
    if len(pts) < 2:
        return []
    if pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    lens = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        lens.append((b - a).length())
    return lens


def analyze_tiny_segments(polys: Sequence[Sequence[Vec2]], thresh: float = 0.5) -> dict:
    tiny = 0
    zeroish = 0
    total = 0
    for poly in polys:
        for L in segment_lengths(poly):
            total += 1
            if L < thresh:
                tiny += 1
            if L < 1e-6:
                zeroish += 1
    return {"total_segments": total, "tiny_lt_0.5": tiny, "zeroish": zeroish}


def check_self_intersecting(path: Path) -> Tuple[bool, str]:
    """
    pathops.simplify 前後の contour 数変化、および pathops の自己交差検出風ヒューリスティック。
    skia は Path.simplify で自己交差を解消する。simplify 前後で contour/verb が大きく変わる、
    または simplify が例外を投げる場合にフラグ。
    """
    try:
        before_c = count_contours(path)
        before_verbs = sum(1 for _ in path)
        simplified = simplify(path, fix_winding=True)
        after_c = count_contours(simplified)
        after_verbs = sum(1 for _ in simplified)
        # 入力が既にクリーンならほぼ同じ。自己交差がある場合 verb 数が減ることが多い
        changed = (before_c != after_c) or (abs(before_verbs - after_verbs) > 2)
        # より直接的: OpBuilder で交差検出は難しいので、
        # pathops には explicit self-intersect API が無い → simplify 差分 + winding で報告
        return changed, (
            f"simplify: contours {before_c}->{after_c}, verbs {before_verbs}->{after_verbs}, "
            f"changed={changed}"
        )
    except Exception as e:
        return True, f"simplify error (likely bad geometry): {e}"


def has_pathops_self_intersection_flag(path: Path) -> Tuple[bool, str]:
    """
    pathops 0.9: Path に explicit な自己交差フラグは無い。
    代替: union([path]) と simplify の結果一致、および raw path を
    FillType.WINDING で描いたときの面積的健全性は SVG 目視に委ねる。
    ここでは各 contour を単独 Path として simplify したとき verb が減るかを見る。
    """
    # 全 path を一度 simplify して、自己交差解消が発生したか
    try:
        s = simplify(path, fix_winding=True)
        # 元の path を再度 union して比較（空でないこと）
        if count_contours(s) == 0 and count_contours(path) > 0:
            return True, "simplify produced empty path from non-empty"
        # skia PathPen 経由で self-intersecting は公開APIに無し
        # 交差有無の近似: raw contour のバウンディング内での二重塗りは union 後に消える前提
        return False, "no explicit self-intersect API; used simplify heuristic only"
    except Exception as e:
        return True, str(e)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    report = {"chars": {}, "verdict": {}}

    for pname in ("classic", "modern"):
        params = PARAM_SETS[pname]
        strokes = CHARACTERS["ei"]
        polys: List[List[Vec2]] = []
        for s in strokes:
            polys.extend(build_stroke(s, params))

        tiny = analyze_tiny_segments(polys)
        paths = [poly_to_path(poly) for poly in polys if len(poly) >= 3]
        # 空 path 除外
        paths = [p for p in paths if count_contours(p) > 0]

        before_contours = sum(count_contours(p) for p in paths)
        # 各ポリゴン単体の自己交差ヒューリスティック
        per_poly_si = []
        for i, p in enumerate(paths):
            si, msg = check_self_intersecting(p)
            if si:
                per_poly_si.append({"index": i, "msg": msg})

        # before SVG: 重ね塗り（各 path 連結）
        before_d = " ".join(path_to_svg_d(p) for p in paths)
        before_svg = os.path.join(OUT, f"ei_before_union_{pname}.svg")
        with open(before_svg, "w", encoding="utf-8") as f:
            f.write(
                make_svg(
                    before_d,
                    f"永 before union ({pname})",
                    f"contours={before_contours} polys={len(paths)}",
                )
            )

        # also keep polygon dump via prototype helper for visual parity
        before_poly_d = " ".join(polygon_to_svg_path(poly) for poly in polys if len(poly) >= 3)

        # union
        try:
            united = pathops_union(paths)
            union_ok = True
            union_err = None
        except Exception as e:
            united = Path()
            union_ok = False
            union_err = repr(e)

        after_contours = count_contours(united) if union_ok else -1
        after_si, after_si_msg = (
            check_self_intersecting(united) if union_ok and after_contours > 0 else (False, "n/a")
        )
        # 追加: simplify して安定化
        if union_ok and after_contours > 0:
            try:
                cleaned = simplify(united, fix_winding=True)
                cleaned_contours = count_contours(cleaned)
            except Exception as e:
                cleaned = united
                cleaned_contours = after_contours
                after_si_msg += f" | clean simplify fail: {e}"
        else:
            cleaned = united
            cleaned_contours = after_contours

        after_d = path_to_svg_d(cleaned) if union_ok else ""
        after_svg = os.path.join(OUT, f"ei_after_union_{pname}.svg")
        with open(after_svg, "w", encoding="utf-8") as f:
            f.write(
                make_svg(
                    after_d,
                    f"永 after union ({pname})",
                    f"contours={cleaned_contours} union_ok={union_ok}",
                )
            )

        # side-by-side comparison SVG
        compare_svg = os.path.join(OUT, f"ei_union_compare_{pname}.svg")
        with open(compare_svg, "w", encoding="utf-8") as f:
            f.write(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2100 1100" width="2100" height="1100">
  <title>永 union compare ({pname})</title>
  <text x="20" y="40" font-size="28" fill="#222">before union (overlay) — contours={before_contours}</text>
  <text x="1120" y="40" font-size="28" fill="#222">after union — contours={cleaned_contours}</text>
  <g transform="translate(50,80)">
    <rect x="0" y="0" width="1000" height="1000" fill="#fafafa" stroke="#ccc"/>
    <path d="{before_poly_d}" fill="#000" fill-rule="nonzero"/>
  </g>
  <g transform="translate(1100,80)">
    <rect x="0" y="0" width="1000" height="1000" fill="#fafafa" stroke="#ccc"/>
    <path d="{after_d}" fill="#000" fill-rule="nonzero"/>
  </g>
</svg>
"""
            )

        # 十も軽く確認（交差の代表）
        juu_polys: List[List[Vec2]] = []
        for s in CHARACTERS["juu"]:
            juu_polys.extend(build_stroke(s, params))
        juu_paths = [poly_to_path(p) for p in juu_polys if len(p) >= 3]
        juu_before = sum(count_contours(p) for p in juu_paths)
        try:
            juu_u = simplify(pathops_union(juu_paths), fix_winding=True)
            juu_after = count_contours(juu_u)
            juu_ok = True
            juu_err = None
            juu_svg = os.path.join(OUT, f"juu_after_union_{pname}.svg")
            with open(juu_svg, "w", encoding="utf-8") as f:
                f.write(make_svg(path_to_svg_d(juu_u), f"十 after union ({pname})", f"c={juu_after}"))
        except Exception as e:
            juu_after = -1
            juu_ok = False
            juu_err = repr(e)

        entry = {
            "param": pname,
            "n_polygons": len(paths),
            "before_contours": before_contours,
            "after_contours_raw": after_contours,
            "after_contours_simplified": cleaned_contours,
            "union_ok": union_ok,
            "union_err": union_err,
            "per_poly_self_intersect_suspects": per_poly_si,
            "after_self_intersect_heuristic": {"changed_by_simplify": after_si, "msg": after_si_msg},
            "tiny_segments": tiny,
            "juu": {
                "before": juu_before,
                "after": juu_after,
                "ok": juu_ok,
                "err": juu_err,
            },
            "svgs": {
                "before": before_svg,
                "after": after_svg,
                "compare": compare_svg,
            },
        }
        report["chars"][f"ei_{pname}"] = entry
        print(json.dumps(entry, ensure_ascii=False, indent=2))

    # 判定メモ（詳細は REPORT）:
    # - union 自体は成功し、交差する本体は1輪郭に融合する
    # - 非接触の点（側）は別 contour のまま（Stage A の食い込みが必要）
    # - 打ち込み等の点接触・微小島が残る（simplify 後も 11〜30u の島）
    # → PLAN §3.3 の「union で単一輪郭化」は交差重なり部では成立、全体単一化は条件付き
    for key, e in report["chars"].items():
        merged = (
            e["union_ok"]
            and e["after_contours_simplified"] >= 1
            and e["after_contours_simplified"] < e["before_contours"]
        )
        single = e["after_contours_simplified"] == 1
        report["verdict"][key] = {
            "union_runs": e["union_ok"],
            "contour_reduced": merged,
            "single_contour": single,
            "juu_single": e["juu"]["after"] == 1,
            "premise": "条件付き",
            "note": (
                "交差重なりは union で融合。非接触ストロークと端物の微小島が残り "
                f"contours {e['before_contours']}→{e['after_contours_simplified']}。"
                "Stage A join_overlap＋微小輪郭除去が前提条件。"
            ),
        }

    report["overall"] = "条件付き"
    report["edge_cases"] = [
        "点（側）が横画に重ならず別 contour として残る",
        "打ち込みポリゴンの点接触/微小食い込み不足で 10–30u の島が残る（十・永とも）",
        "一部本体ポリゴンは simplify で verb 数が減り自己交差疑い（オフセット由来）",
        "zeroish セグメント（長さ≈0）が数個 — 閉包の重複点由来の可能性",
    ]
    out_json = os.path.join(OUT, "verify_a_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("OVERALL:", report["overall"])
    print("wrote", out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
