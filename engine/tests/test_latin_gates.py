"""G-O、G-M、G-SET。帯は様式の値。測った数値の凍結ファイルは作らない。"""

from __future__ import annotations

import pytest
from PIL import Image

from engine.geometry import Vec2
from engine.latin.build import GlyphOutline, build_glyph
from engine.latin.gate import (
    ink_area,
    line_gap_area,
    metric_violations,
    overshoot_violations,
    side_gaps,
    stem_set_violations,
    thinnest_run,
)
from engine.latin.load import load_resolved
from engine.latin.sheet import render_pilot_sheet, text_origins

GLYPHS = ("H", "O", "B", "V", "S", "zero")
STYLES = ("modern", "classic", "chic", "pop")


def _shift(outline: GlyphOutline, dx: float, dy: float) -> GlyphOutline:
    moved = tuple(
        tuple(Vec2(point.x + dx, point.y + dy) for point in contour)
        for contour in outline.contours
    )
    return GlyphOutline(outline.glyph, outline.advance, moved, outline.holes)


def _box(width: float) -> GlyphOutline:
    contour = (
        Vec2(0.0, 0.0),
        Vec2(width, 0.0),
        Vec2(width, 700.0),
        Vec2(0.0, 700.0),
    )
    return GlyphOutline("box", width, (contour,), (False,))


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("glyph", GLYPHS)
def test_pilot_overshoot_stays_inside_the_style_band(glyph, style):
    resolved = load_resolved(glyph, style)
    violations = overshoot_violations(build_glyph(resolved), resolved)
    assert violations == []


def test_overshoot_past_the_band_is_listed():
    resolved = load_resolved("O", "modern")
    violations = overshoot_violations(
        _shift(build_glyph(resolved), 0.0, 20.0), resolved
    )
    assert violations


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("glyph", GLYPHS)
def test_pilot_bbox_fits_the_vertical_metrics(glyph, style):
    resolved = load_resolved(glyph, style)
    assert metric_violations(build_glyph(resolved), resolved.style) == []


def test_bbox_past_the_ascender_is_listed():
    resolved = load_resolved("H", "modern")
    violations = metric_violations(
        _shift(build_glyph(resolved), 0.0, 200.0), resolved.style
    )
    assert any("ascender" in item for item in violations)


def test_pilot_vertical_stems_stay_within_five_percent():
    for style in STYLES:
        outlines = {glyph: build_glyph(load_resolved(glyph, style)) for glyph in GLYPHS}
        assert stem_set_violations(outlines) == []


def test_a_stem_outside_five_percent_is_listed():
    stem = build_glyph(load_resolved("H", "modern"))
    assert "box" in stem_set_violations({"H": stem, "box": _box(40.0)})


def test_ink_area_subtracts_the_hole():
    outer = (Vec2(0.0, 0.0), Vec2(10.0, 0.0), Vec2(10.0, 10.0), Vec2(0.0, 10.0))
    hole = (Vec2(2.0, 2.0), Vec2(2.0, 6.0), Vec2(6.0, 6.0), Vec2(6.0, 2.0))
    outline = GlyphOutline("box", 10.0, (outer, hole), (False, True))
    assert ink_area(outline) == pytest.approx(100.0 - 16.0)


def test_thinnest_run_is_the_narrower_stem():
    outline = build_glyph(load_resolved("H", "pop"))
    assert thinnest_run(outline, 200.0) == pytest.approx(154.0, abs=1.0)


def test_text_row_starts_each_glyph_at_its_advance():
    assert text_origins([100.0, 40.0, 25.0]) == [0.0, 100.0, 140.0]


def _pilot(glyph: str, style: str):
    return build_glyph(load_resolved(glyph, style))


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("glyph", GLYPHS)
def test_ink_side_margins_are_not_negative(glyph, style):
    left, right = side_gaps(_pilot(glyph, style))
    assert left >= 0.0
    assert right >= 0.0


@pytest.mark.parametrize("style", STYLES)
def test_diagonal_sits_closer_than_round_and_round_closer_than_straight(style):
    straight = side_gaps(_pilot("H", style))
    round_ = side_gaps(_pilot("O", style))
    diagonal = side_gaps(_pilot("V", style))
    assert diagonal[0] < round_[0] < straight[0]
    assert diagonal[1] < round_[1] < straight[1]


@pytest.mark.parametrize("style", STYLES)
def test_hoh_and_oho_have_the_same_gap_area(style):
    """対は同じ（H–O と O–H）なので、面積は一致する。帯にはまだしない。"""
    hoh = line_gap_area([_pilot("H", style), _pilot("O", style), _pilot("H", style)])
    oho = line_gap_area([_pilot("O", style), _pilot("H", style), _pilot("O", style)])
    assert hoh > 0.0
    assert oho == pytest.approx(hoh, rel=0.001)


def test_pilot_sheet_includes_the_spacing_lines(tmp_path):
    path = render_pilot_sheet(tmp_path / "pilot_sheet.png")
    image = Image.open(path)
    assert image.width > 500
    assert image.height > 4000
