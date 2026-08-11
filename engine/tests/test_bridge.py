"""T7 bridge: 座標変換・向き・一時フォント化。"""

from __future__ import annotations

from pathlib import Path

import pytest

ufoLib2 = pytest.importorskip("ufoLib2")
pytest.importorskip("fontmake")
pytest.importorskip("freetype")

from engine.bridge import (
    CORE_GLYPHS,
    EXTRA_GLYPHS,
    build_temp_font,
    nesting_depths,
    normalize_fill_winding,
    shoelace,
    solve_to_font_contours,
    to_font_contours,
)
from engine.geometry import COORDINATE_SPACE, UPM, y_for_font
from engine.params import CLASSIC, PRODUCT_R1


def test_to_font_contours_flips_legacy_y():
    assert COORDINATE_SPACE == "svg_y_down_legacy"
    font = to_font_contours([[(100.0, 200.0), (300.0, 200.0), (300.0, 400.0)]])
    assert font[0][0] == (100.0, y_for_font(200.0))
    assert font[0][0][1] == UPM - 200.0


def test_extract_contours_xy_rejects_cubic():
    """Phase 0c: CUBIC を黙って潰さず raise。"""
    from pathops import Path

    from engine.bridge import extract_contours_xy

    p = Path()
    p.moveTo(0, 0)
    p.cubicTo(10, 0, 10, 10, 0, 10)
    p.close()
    with pytest.raises(ValueError, match="CUBIC verb not supported"):
        extract_contours_xy(p)


def test_normalize_fill_winding_bulk_reverse_outer():
    # Y反転後の外形（負面積）→ 一括 reverse で正へ
    cw = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
    assert shoelace(cw) < 0
    out, meta = normalize_fill_winding([cw])
    assert shoelace(out[0]) > 0
    assert meta["strategy"] == "bulk-reverse-verify"
    assert meta["reversed"] == [True]
    assert meta["depths"] == [0]
    assert meta["n_holes"] == 0


def test_normalize_fill_winding_preserves_hole():
    # Y反転直後の状態: 外形=負・穴=正 → reverse 後 外形=正・穴=負
    outer = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)]  # CW = 負
    hole = [(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)]  # CCW = 正
    assert shoelace(outer) < 0
    assert shoelace(hole) > 0
    out, meta = normalize_fill_winding([outer, hole])
    assert shoelace(out[0]) > 0
    assert shoelace(out[1]) < 0
    assert meta["depths"] == [0, 1]
    assert meta["n_holes"] == 1


def test_normalize_fill_winding_rejects_same_winding_nest():
    # 同巻き入れ子（両方負）→ 検証で raise
    outer = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)]
    inner = [(20.0, 20.0), (20.0, 80.0), (80.0, 80.0), (80.0, 20.0)]
    assert shoelace(outer) < 0
    assert shoelace(inner) < 0
    with pytest.raises(ValueError, match="winding verify failed"):
        normalize_fill_winding([outer, inner])


def test_nesting_depths_two_outers():
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    b = [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)]
    assert nesting_depths([a, b]) == [0, 0]


def test_rep_point_inside_concave_c_shape():
    """C字（頂点平均が外）でも包含用代表点が輪郭内に落ちる。"""
    from engine.bridge import _point_in_poly, _rep_point

    # 右開きの C（太いリングの左半分）
    c = [
        (0.0, 0.0),
        (80.0, 0.0),
        (80.0, 20.0),
        (20.0, 20.0),
        (20.0, 80.0),
        (80.0, 80.0),
        (80.0, 100.0),
        (0.0, 100.0),
    ]
    avg = (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))
    assert not _point_in_poly(avg[0], avg[1], c), "precondition: avg outside"
    rx, ry = _rep_point(c)
    assert _point_in_poly(rx, ry, c)


def test_solve_juu_has_single_contour():
    gr = solve_to_font_contours("juu", CLASSIC)
    assert gr.contours_after_cleanup == 1
    assert len(gr.font_contours) == 1
    assert all(shoelace(c) > 0 for c in gr.font_contours)
    assert gr.winding.get("n_holes") == 0


def test_solve_kuchi_keeps_hole_winding():
    """口: 外形正・穴負（Phase 0a の現在バグ修正）。"""
    gr = solve_to_font_contours("kuchi", PRODUCT_R1)
    assert len(gr.font_contours) == 2
    areas = [shoelace(c) for c in gr.font_contours]
    positives = [a for a in areas if a > 0]
    negatives = [a for a in areas if a < 0]
    assert len(positives) == 1
    assert len(negatives) == 1
    assert abs(positives[0]) > abs(negatives[0])
    assert gr.winding.get("n_holes") == 1


@pytest.mark.parametrize("gid", ["kuchi", "nichi", "ta", "naka"])
def test_hole_glyphs_have_negative_contour(gid: str):
    gr = solve_to_font_contours(gid, PRODUCT_R1)
    areas = [shoelace(c) for c in gr.font_contours]
    assert any(a < 0 for a in areas), f"{gid}: no hole (all areas={areas})"
    assert any(a > 0 for a in areas)


def test_build_temp_font_classic(tmp_path: Path):
    result = build_temp_font(
        "classic",
        glyph_ids=list(CORE_GLYPHS.keys()),
        out_root=tmp_path / "classic",
    )
    assert result.otf_path.is_file()
    assert result.otf_path.stat().st_size > 1000
    assert result.fill_check.get("ok") is True
    assert result.fill_check.get("inverted_suspect") is False
    for g in result.glyphs:
        assert g.glyph_id in CORE_GLYPHS


def test_build_temp_font_product_r1(tmp_path: Path):
    result = build_temp_font(
        "product_r1",
        glyph_ids=["juu"],
        out_root=tmp_path / "product_r1",
    )
    assert result.otf_path.is_file()
    assert result.fill_check.get("ok") is True
    # product_r1 は縦画が太い → コントラストが取れること（probe があれば）
    m = result.measure_juu
    if m.get("status") == "ok" and m.get("contrast_v_over_h") is not None:
        assert m["contrast_v_over_h"] > 1.5
    assert PRODUCT_R1.v_thickness == 110.0


def test_build_temp_font_kuchi_hole_is_white(tmp_path: Path):
    """口の OTF ラスタでカウンター中心が白（穴保持の端到端）。"""
    import freetype
    import numpy as np

    result = build_temp_font(
        "product_r1",
        glyph_ids=["kuchi"],
        out_root=tmp_path / "kuchi",
    )
    assert result.otf_path.is_file()
    assert "kuchi" in EXTRA_GLYPHS

    em = 256
    face = freetype.Face(str(result.otf_path))
    face.set_pixel_sizes(em, em)
    face.load_char("口", freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bm = face.glyph.bitmap
    assert bm.width > 0 and bm.rows > 0
    gray = np.array(bm.buffer, dtype=np.uint8).reshape(bm.rows, bm.width)
    # グリフ bbox 中央近傍の小さな窓の中央値が低インク（白）
    cy, cx = bm.rows // 2, bm.width // 2
    win = gray[max(0, cy - 4) : cy + 5, max(0, cx - 4) : cx + 5]
    assert win.size > 0
    assert float(win.mean()) < 64.0, f"counter not white: mean={win.mean():.1f}"
