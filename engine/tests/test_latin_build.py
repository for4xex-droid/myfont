"""パイロット6字が様式ごとに輪郭を返す。"""

from __future__ import annotations

import pytest

from engine.latin.build import build_glyph
from engine.latin.load import load_resolved

GLYPHS = ("H", "O", "B", "V", "S", "zero")
STYLES = ("modern", "classic", "chic", "pop")


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("glyph", GLYPHS)
def test_pilot_glyph_matches_expected_contours(glyph, style):
    resolved = load_resolved(glyph, style)
    outline = build_glyph(resolved)
    assert outline.contour_count == resolved.skeleton.expect_contours
    assert outline.hole_count == resolved.skeleton.expect_holes
    assert outline.advance > 0


def test_pop_h_is_heavier_than_modern_and_chic_o_is_narrower():
    def ink(glyph, style):
        outline = build_glyph(load_resolved(glyph, style))
        return sum(abs(_area(c)) for c in outline.contours)

    def _area(points):
        a = 0.0
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            a += points[i].x * points[j].y - points[j].x * points[i].y
        return 0.5 * a

    assert ink("H", "pop") > ink("H", "modern") * 1.3
    modern_o = build_glyph(load_resolved("O", "modern"))
    chic_o = build_glyph(load_resolved("O", "chic"))
    def width(outline):
        xs = [p.x for c in outline.contours for p in c]
        return max(xs) - min(xs)
    assert width(chic_o) < width(modern_o) * 0.85
