"""Phase 1: cubic_fit（折れ線→角ロック cubic）。"""

from __future__ import annotations

import pytest

from engine.bridge import solve_to_font_contours
from engine.curve_fit import ContourPath, fit_closed_contour
from engine.curve_refit import RefitConfig, load_refit_config, refit_contours
from engine.params import PRODUCT_R1


def test_load_config_kana_mode_cubic_fit():
    cfg = load_refit_config()
    assert cfg.kana_mode == "cubic_fit"
    assert cfg.mode == "rdp_polyline"  # 漢字は据え置き
    assert cfg.cubic_max_error_upm <= 0.5 + 1e-9
    assert cfg.cubic_loop_max_error_upm >= cfg.cubic_max_error_upm


def test_fit_smooth_oval_under_gates():
    import math

    pts = [
        (500 + 220 * math.cos(t), 500 + 160 * math.sin(t))
        for t in [i * 2 * math.pi / 72 for i in range(72)]
    ]
    path, meta = fit_closed_contour(
        pts, max_error_upm=0.5, corner_deg=30.0, max_anchors=48
    )
    assert isinstance(path, ContourPath)
    assert meta["max_error"] <= 0.5 + 1e-6
    assert meta["anchor_count"] <= 48
    assert meta["n_cubic"] >= 1


@pytest.mark.parametrize("gid", ["ku", "shi", "tsu"])
def test_kana_simple_cubic_fit_dod(gid: str):
    """単画仮名: Hausdorff≤yaml上限・anchors≤40・contour数1。"""
    cfg = load_refit_config()
    gr = solve_to_font_contours(gid, PRODUCT_R1)
    assert gr.refit.get("mode") == "cubic_fit"
    assert gr.font_paths is not None
    assert len(gr.font_paths) == 1
    assert gr.refit["max_error"] <= 0.5 + 1e-6
    assert gr.refit["per_contour"][0]["anchor_count"] <= 40
    assert gr.refit.get("self_intersect") is False


def test_no_loop_has_hole_and_cubic_fit():
    """8c「の」: solve 穴1＋cubic_fit 通過。"""
    cfg = load_refit_config()
    gr = solve_to_font_contours("no", PRODUCT_R1)
    assert gr.winding.get("n_holes") == 1
    assert len(gr.font_contours) == 2
    assert gr.refit.get("mode") == "cubic_fit"
    assert gr.refit["max_error"] <= cfg.cubic_loop_max_error_upm + 1e-6
    for pc in gr.refit["per_contour"]:
        assert pc["anchor_count"] <= cfg.cubic_max_anchors


@pytest.mark.parametrize("gid", ["to", "i"])
def test_kana_join_cubic_fit_gates(gid: str):
    """接合字: 誤差ゲート＋角レポート＋アンカー上限（yaml）。"""
    cfg = load_refit_config()
    gr = solve_to_font_contours(gid, PRODUCT_R1)
    assert gr.refit.get("mode") == "cubic_fit"
    assert gr.font_paths is not None
    assert gr.refit["max_error"] <= 0.5 + 1e-6
    for pc in gr.refit["per_contour"]:
        assert pc["anchor_count"] <= cfg.cubic_max_anchors
        assert pc["n_corners"] >= 2
        # 角ヒット位置をレポート（DoD）
        assert "corners" in pc


def test_cubic_fit_reproducible():
    gr1 = solve_to_font_contours("ku", PRODUCT_R1)
    gr2 = solve_to_font_contours("ku", PRODUCT_R1)
    assert gr1.refit["max_error"] == gr2.refit["max_error"]
    assert gr1.refit["total_anchors"] == gr2.refit["total_anchors"]
    assert len(gr1.font_paths[0].segs) == len(gr2.font_paths[0].segs)


def test_refit_contours_cubic_preserves_count():
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    # 辺に中間点
    dense = []
    for a, b in zip(square, square[1:] + square[:1]):
        for t in range(8):
            u = t / 8
            dense.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
    cfg = RefitConfig(
        mode="cubic_fit",
        cubic_max_error_upm=0.5,
        cubic_corner_deg=20.0,
        cubic_max_anchors=40,
    )
    out = refit_contours([dense], cfg)
    assert out.paths is not None
    assert len(out.paths) == 1
    assert out.meta["max_error"] <= 0.5 + 1e-6
