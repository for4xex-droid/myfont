"""仮名観測メトリクス（Phase 0b）。合否には接続しない。"""

from __future__ import annotations

import math
from typing import Any

from engine.geometry import (
    curvature_radii,
    sample_cubic_chain,
    smooth_tangents,
)
from engine.kana.load import KANA_GLYPH_META, kana_characters, load_kana_skeleton
from engine.params import MinchoParams, PARAM_SETS
from engine.strokes import SkeletonStroke


def _percentile(sorted_vals: list[float], p: float) -> float:
    """p∈[0,100]。線形補間パーセンタイル。"""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    x = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return sorted_vals[lo]
    t = x - lo
    return sorted_vals[lo] * (1.0 - t) + sorted_vals[hi] * t


def spine_curvature_stats(
    strokes: list[SkeletonStroke],
    *,
    n_per_seg: int = 48,
) -> dict[str, Any]:
    """全 element spine の離散曲率 κ=1/R の統計（観測専用）。"""
    kappas: list[float] = []
    min_radius = float("inf")
    for s in strokes:
        samples = smooth_tangents(sample_cubic_chain(list(s.points), n_per_seg=n_per_seg))
        radii = curvature_radii(samples)
        for r in radii:
            if math.isfinite(r) and r > 1e-9:
                min_radius = min(min_radius, r)
                kappas.append(1.0 / r)
    kappas.sort()
    return {
        "curvature_p95": _percentile(kappas, 95.0) if kappas else None,
        "curvature_p50": _percentile(kappas, 50.0) if kappas else None,
        "curvature_max": kappas[-1] if kappas else None,
        "min_radius_upm": (min_radius if math.isfinite(min_radius) else None),
        "n_curvature_samples": len(kappas),
    }


def outline_point_stats(
    glyph_id: str,
    params: MinchoParams | str = "product_r1",
) -> dict[str, Any]:
    """製品輪郭（refit 後）の点数。polyline 時代は anchor_count≈points_after。"""
    from engine.bridge import solve_to_font_contours

    if isinstance(params, str):
        params_name = params
        params_obj = PARAM_SETS[params_name]
    else:
        params_name = "custom"
        params_obj = params

    gr = solve_to_font_contours(glyph_id, params_obj)
    per = [len(c) for c in gr.font_contours]
    points_after = sum(per)
    refit = gr.refit or {}
    from engine.join_solver import polygon_signed_area

    signed = [polygon_signed_area(c) for c in gr.font_contours]
    # 正面積＝外形の囲い（穴を含む）。インクは外形−穴。
    outer_area = sum(a for a in signed if a > 0)
    hole_area = sum(-a for a in signed if a < 0)
    ink_area = outer_area - hole_area
    hole_area_ratio = (hole_area / outer_area) if outer_area > 1e-9 else None
    per_refit = refit.get("per_contour") or []
    refit_anchors = sum(int(pc.get("anchor_count") or 0) for pc in per_refit)
    return {
        "params": params_name,
        "n_contours": len(per),
        "points_per_contour": per,
        "points_after": points_after,
        "anchor_count": refit_anchors if refit_anchors > 0 else points_after,
        "segment_count": max(0, points_after - len(per)) if per else 0,
        "refit_mode": refit.get("mode"),
        "refit_points_before": refit.get("points_before"),
        "refit_points_after": refit.get("points_after", points_after),
        "n_holes": gr.winding.get("n_holes"),
        "winding_strategy": gr.winding.get("strategy"),
        # 合否非接続。参照帯未凍結（掟8）なのでゲートにしない
        "hole_area_upm2": hole_area if hole_area > 0 else 0.0,
        "outer_area_upm2": outer_area,
        "ink_area_upm2": ink_area,
        "hole_area_ratio": hole_area_ratio,
    }


def observe_glyph(
    glyph_id: str,
    params: MinchoParams | str = "product_r1",
    *,
    yaml_path=None,
) -> dict[str, Any]:
    """ゲート合否と独立の観測ブロック。"""
    if isinstance(params, str):
        params_name = params
        params_obj = PARAM_SETS[params_name]
    else:
        params_name = "custom"
        params_obj = params

    if yaml_path is not None:
        gid, strokes, _meta = load_kana_skeleton(yaml_path)
        glyph_id = gid
    else:
        chars = kana_characters()
        if glyph_id not in chars:
            return {
                "glyph_id": glyph_id,
                "params": params_name,
                "error": f"unknown glyph {glyph_id}",
            }
        strokes = list(chars[glyph_id])
        # ensure meta warm
        _ = KANA_GLYPH_META.get(glyph_id)

    curv = spine_curvature_stats(strokes)
    try:
        outline = outline_point_stats(glyph_id, params_obj)
    except Exception as e:  # noqa: BLE001 — 観測は fail-open
        outline = {"error": f"{type(e).__name__}: {e}"}

    return {
        "glyph_id": glyph_id,
        "params": params_name,
        "observation_only": True,
        "curvature": curv,
        "outline": outline,
    }
