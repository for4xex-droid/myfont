"""P2++: union 後の曲線再適合ゲート。"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.bridge import extract_contours_xy, solve_to_font_contours
from engine.curve_refit import (
    RefitConfig,
    load_refit_config,
    max_deviation,
    rdp_closed,
    refit_contours,
)
from engine.extra_skeletons import all_characters
from engine.join_solver import solve_glyph
from engine.params import CLASSIC, PRODUCT_R1


def test_load_refit_config_defaults_to_rdp_polyline():
    cfg = load_refit_config()
    assert cfg.mode == "rdp_polyline"
    assert cfg.enabled is True
    assert cfg.epsilon_upm > 0


def test_load_refit_config_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="curve_refit"):
        load_refit_config(tmp_path / "nope.yaml")


def test_rdp_reduces_square_with_colinear():
    # 正方形の各辺に中間点を入れた輪郭 → 4頂点へ
    pts = [
        (0.0, 0.0),
        (50.0, 0.0),
        (100.0, 0.0),
        (100.0, 50.0),
        (100.0, 100.0),
        (50.0, 100.0),
        (0.0, 100.0),
        (0.0, 50.0),
    ]
    out = rdp_closed(pts, epsilon=0.5)
    assert len(out) == 4
    assert max_deviation(pts, out) <= 0.5 + 1e-6


def test_refit_gate_rejects_loose_error(monkeypatch: pytest.MonkeyPatch):
    # RDP が形状を壊した結果をゲートが弾くこと
    def bad_rdp(points, epsilon):
        return [(0.0, 0.0), (100.0, 0.0), (50.0, 1.0)]

    monkeypatch.setattr("engine.curve_refit.rdp_closed", bad_rdp)
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    cfg = RefitConfig(mode="rdp_polyline", epsilon_upm=1.5, max_error_upm=1.5)
    with pytest.raises(ValueError, match="curve_refit gate failed"):
        refit_contours([square], cfg)


def test_juu_refit_reduces_points_and_keeps_one_contour():
    chars = all_characters()
    raw = extract_contours_xy(solve_glyph(chars["juu"], PRODUCT_R1).path)
    assert len(raw) == 1
    before = sum(len(c) for c in raw)
    out = refit_contours(raw, load_refit_config())
    assert out.meta["n_contours"] == 1
    assert out.meta["points_after"] < before
    assert out.meta["max_error"] <= load_refit_config().max_error_upm + 1e-6


@pytest.mark.parametrize("params", [CLASSIC, PRODUCT_R1])
@pytest.mark.parametrize("gid", ["juu", "ni", "ei", "hon", "ta"])
def test_bridge_refit_preserves_contour_count(params, gid):
    gr = solve_to_font_contours(gid, params)
    # refit は extract 後輪郭数を維持。after_cleanup は solver 報告値（通常一致）
    assert gr.refit.get("n_contours") == len(gr.font_contours)
    assert gr.refit.get("points_after", 0) <= gr.refit.get("points_before", 0)
    assert gr.contours_after_cleanup == len(gr.font_contours)


def test_passthrough_mode_keeps_all_points():
    chars = all_characters()
    raw = extract_contours_xy(solve_glyph(chars["juu"], CLASSIC).path)
    cfg = RefitConfig(mode="passthrough", enabled=True)
    out = refit_contours(raw, cfg)
    assert out.meta["points_after"] == out.meta["points_before"]
