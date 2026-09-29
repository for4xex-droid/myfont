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


def _turns(contour):
    import math

    pts = list(contour)
    if len(pts) > 1 and pts[0].x == pts[-1].x and pts[0].y == pts[-1].y:
        pts = pts[:-1]
    found = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        v1 = (b.x - a.x, b.y - a.y)
        v2 = (c.x - b.x, c.y - b.y)
        found.append(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    return found


def test_modern_b_waist_is_not_a_spike():
    outline = build_glyph(load_resolved("B", "modern"))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    assert min(_turns(outer)) > -100


def _tip_rise(style: str) -> float:
    outer = build_glyph(load_resolved("V", style)).contours[0]
    ymin = min(point.y for point in outer)
    band = [point for point in outer if point.y < ymin + 12]
    return max(point.y for point in band) - ymin


def test_modern_v_tip_has_no_valley():
    assert _tip_rise("modern") < 4


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_v_tip_is_level(style):
    assert _tip_rise(style) < 4


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_v_tip_has_no_side_stub(style):
    outer = build_glyph(load_resolved("V", style)).contours[0]
    ymin = min(point.y for point in outer)
    flat = [point for point in outer if point.y < ymin + 2]
    right = max(point.x for point in flat)
    stub = [point for point in outer if ymin + 2 <= point.y < ymin + 40 and point.x > right + 18]
    assert stub == []


@pytest.mark.parametrize("style", STYLES)
def test_round_o_bottom_stays_curved(style):
    outline = build_glyph(load_resolved("O", style))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    ymin = min(point.y for point in outer)
    low = [point for point in outer if point.y < ymin + 8]
    assert max(point.y for point in low) - ymin > 2


def test_modern_b_bowls_do_not_stick_out_of_the_stem():
    resolved = load_resolved("B", "modern")
    outline = build_glyph(resolved)
    style = resolved.style
    width = style.proportions["B"] * style.cap_height
    left = style.sidebearing["base"] * style.cap_height * style.sidebearing["straight"]
    stem_left = left + 0.18 * width - (style.cap_height * resolved.pen.stem / 2.0)
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    assert min(point.x for point in outer) >= stem_left - 2.0


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
