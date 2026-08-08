"""T7 bridge: 座標変換・向き・一時フォント化。"""

from __future__ import annotations

from pathlib import Path

import pytest

ufoLib2 = pytest.importorskip("ufoLib2")
pytest.importorskip("fontmake")
pytest.importorskip("freetype")

from engine.bridge import (
    CORE_GLYPHS,
    build_temp_font,
    ensure_positive_fill,
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


def test_ensure_positive_fill_reverses_cw():
    # CW square in font space → negative shoelace → reverse
    cw = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
    assert shoelace(cw) < 0
    out, meta = ensure_positive_fill([cw])
    assert shoelace(out[0]) > 0
    assert meta["reversed"] == [True]


def test_solve_juu_has_single_contour():
    gr = solve_to_font_contours("juu", CLASSIC)
    assert gr.contours_after_cleanup == 1
    assert len(gr.font_contours) == 1
    assert all(shoelace(c) > 0 for c in gr.font_contours)


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
