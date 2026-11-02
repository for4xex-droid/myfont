"""モダンの直線5字（I L T E F）。平らなので天地にオーバーシュートはない。"""

from __future__ import annotations

import statistics
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from engine.latin.build import build_glyph
from engine.latin.compile import build_style, outline_gap
from engine.latin.gate import (
    metric_violations,
    overshoot_violations,
    side_gaps,
    stem_set_violations,
    vertical_stem_widths,
)
from engine.latin.load import load_resolved
from engine.latin.outline import _missing_extrema, fit_outline

_GLYPHS = ("I", "L", "T", "E", "F")
_CAP = 700.0
_BAR_Y = 0.52


def _built(glyph: str):
    return build_glyph(load_resolved(glyph, "modern"))


def _area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    count = len(points)
    for index in range(count):
        nxt = points[(index + 1) % count]
        total += points[index][0] * nxt[1] - nxt[0] * points[index][1]
    return 0.5 * total


def _bands_at(outline, x: float) -> list[tuple[float, float]] | None:
    """縦の線が横切る墨の、下端と上端。垂直の辺の上では測らない。"""
    ys: list[float] = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            if (start.x - x) * (end.x - x) > 0.0 or abs(end.x - start.x) < 1e-9:
                continue
            t = (x - start.x) / (end.x - start.x)
            if 0.0 <= t < 1.0:
                ys.append(start.y + (end.y - start.y) * t)
    ys.sort()
    if not ys or len(ys) % 2:
        return None
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys), 2)]


def _scans(outline, count: int) -> list[list[tuple[float, float]]]:
    xs = [point.x for contour in outline.contours for point in contour]
    lo, hi = min(xs), max(xs)
    found = []
    for step in range(1, 48):
        bands = _bands_at(outline, lo + (hi - lo) * step / 48)
        if bands is not None and len(bands) == count:
            found.append(bands)
    return found


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_straight_glyph_matches_expected_contours(glyph):
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    assert outline.contour_count == resolved.skeleton.expect_contours
    assert outline.hole_count == resolved.skeleton.expect_holes
    assert outline.advance > 0


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_straight_fit_stays_on_axis_lines(glyph):
    """G-X・G-F・G-L。フィットが通ることと、直線が軸に平行なこと。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert paths
    assert all(_missing_extrema(path) == 0 for path in paths)
    limit = int(resolved.style.curve["max_anchors_per_contour"])
    assert all(len(path.segs) <= limit for path in paths)
    for path in paths:
        cur = path.start
        for seg in path.segs:
            assert seg[0] == "L"
            end = (seg[1], seg[2])
            assert end[0] == cur[0] or end[1] == cur[1]
            cur = end


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_straight_contours_start_at_the_lowest_point_and_wind(glyph):
    """G-ORD。開始点は最も低い点、外形は反時計回り。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    origins = []
    areas = []
    for path in paths:
        points = path.on_curve_points()
        lowest = min(points, key=lambda point: (point[1], point[0]))
        assert points[0] == lowest
        origins.append(lowest)
        areas.append(_area(points))
    assert origins == sorted(origins, key=lambda point: (point[1], point[0]))
    outer = max(range(len(areas)), key=lambda index: abs(areas[index]))
    assert areas[outer] > 0.0
    assert all(area < 0.0 for index, area in enumerate(areas) if index != outer)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_flat_letters_sit_on_the_baseline_and_the_cap(glyph):
    """平らな字の天地は 0 とキャップちょうど。はみ出しは付けない。"""
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    ys = [point.y for contour in outline.contours for point in contour]
    assert min(ys) == pytest.approx(0.0, abs=0.5)
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert overshoot_violations(outline, resolved) == []
    assert metric_violations(outline, resolved.style) == []


def test_vertical_stems_stay_within_five_percent_of_h():
    """G-SET。縦ステムの中央値はパイロットの H から 5% 以内。"""
    outlines = {"H": _built("H")}
    outlines.update({glyph: _built(glyph) for glyph in _GLYPHS})
    middle = statistics.median(vertical_stem_widths(outlines["H"]))
    assert middle > 0.0
    for glyph in _GLYPHS:
        widths = vertical_stem_widths(outlines[glyph])
        assert widths
        found = statistics.median(widths)
        assert abs(found - middle) / middle <= 0.05
    assert stem_set_violations(outlines) == []


def _arm_bands(glyph: str, count: int):
    """腕を全部横切る位置。帯は下から。どの位置でも高さが揃う。"""
    found = _scans(_built(glyph), count)
    assert found
    ref = found[len(found) // 2]
    for bands in found:
        for (lo, hi), (ref_lo, ref_hi) in zip(bands, ref, strict=True):
            assert lo == pytest.approx(ref_lo, abs=1.0)
            assert hi == pytest.approx(ref_hi, abs=1.0)
    return ref


@pytest.mark.parametrize("glyph", ("E", "F"))
def test_middle_bar_follows_bar_y_and_the_arms_stay_put(glyph):
    """中棒の中心は bar_y × cap。天の腕はそこへ動かない。"""
    count = 3 if glyph == "E" else 2
    bands = _arm_bands(glyph, count)
    bar = bands[1] if glyph == "E" else bands[0]
    top = bands[-1]
    assert (bar[0] + bar[1]) / 2 == pytest.approx(_BAR_Y * _CAP, abs=1.0)
    assert top[1] == pytest.approx(_CAP, abs=0.5)
    assert (top[0] + top[1]) / 2 == pytest.approx(_CAP - (bar[1] - bar[0]) / 2, abs=1.5)
    assert abs((top[0] + top[1]) / 2 - _BAR_Y * _CAP) > 100
    if glyph == "E":
        bottom = bands[0]
        assert bottom[0] == pytest.approx(0.0, abs=0.5)
        assert (bottom[0] + bottom[1]) / 2 < 100
        assert abs((bottom[1] - bottom[0]) - (bar[1] - bar[0])) < 1.5


@pytest.mark.parametrize("glyph", ("E", "F"))
def test_middle_bar_ignores_the_skeleton_height(glyph):
    resolved = load_resolved(glyph, "modern")
    strokes = tuple(
        replace(stroke, knots=tuple(replace(knot, y=0.30) for knot in stroke.knots))
        if stroke.role == "bar"
        else stroke
        for stroke in resolved.skeleton.strokes
    )
    moved = replace(resolved, skeleton=replace(resolved.skeleton, strokes=strokes))
    count = 3 if glyph == "E" else 2
    bands = _scans(build_glyph(moved), count)
    assert bands
    chosen = bands[len(bands) // 2]
    bar = chosen[1] if glyph == "E" else chosen[0]
    assert (bar[0] + bar[1]) / 2 == pytest.approx(_BAR_Y * _CAP, abs=1.0)


def test_l_foot_stays_on_the_baseline():
    """地の腕は bar_y へ寄らず、外縁がベースラインに残る。"""
    feet = [
        bands[0] for bands in _scans(_built("L"), 1) if bands[0][1] - bands[0][0] < 120
    ]
    assert feet
    assert all(band[0] == pytest.approx(0.0, abs=0.5) for band in feet)
    assert all((band[0] + band[1]) / 2 < 100 for band in feet)


def test_t_bar_stays_on_the_cap():
    """天の横画は bar_y へ寄らず、外縁がキャップに残る。"""
    bars = [
        bands[0]
        for bands in _scans(_built("T"), 1)
        if bands[0][1] > 650 and bands[0][1] - bands[0][0] < 120
    ]
    assert bars
    assert all(band[1] == pytest.approx(_CAP, abs=0.5) for band in bars)
    assert all((band[0] + band[1]) / 2 > 600 for band in bars)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_side_gaps_are_not_negative(glyph):
    """左右の余白は、骨格の側面を墨の外側に足した量。"""
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    left, right = side_gaps(outline)
    style = resolved.style
    cap = style.cap_height
    expect_left = (
        style.sidebearing["base"] * cap * style.sidebearing[resolved.skeleton.sides[0]]
    )
    expect_right = (
        style.sidebearing["base"] * cap * style.sidebearing[resolved.skeleton.sides[1]]
    )
    assert left >= 0.0
    assert right >= 0.0
    assert left == pytest.approx(expect_left, abs=0.5)
    assert right == pytest.approx(expect_right, abs=0.5)


def test_i_ink_width_is_the_stem():
    """幹1本の I は、proportions ではなくペンの太さが墨の幅になる。"""
    resolved = load_resolved("I", "modern")
    outline = build_glyph(resolved)
    left, right = side_gaps(outline)
    ink = outline.advance - left - right
    assert ink == pytest.approx(resolved.pen.stem * resolved.style.cap_height, abs=1.0)


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return build_style("modern", glyphs=_GLYPHS, out_dir=root)


def _design(glyph: str):
    resolved = load_resolved(glyph, "modern")
    return fit_outline(build_glyph(resolved), resolved.style)


@pytest.mark.parametrize("kind", ("otf", "ttf"))
@pytest.mark.parametrize("glyph", _GLYPHS)
def test_shipped_straight_outline_stays_on_the_design(compiled, glyph, kind):
    """G-TT。最大 ≤ 1.0、平均は 0 以上 0.3 以下。"""
    worst, mean = outline_gap(_design(glyph), compiled[kind], glyph)
    assert worst <= 1.0
    assert 0.0 <= mean <= 0.3
