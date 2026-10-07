"""V の先端は外縁と切り口で決まる。脚の縁は直線で、太さは脚全体で一次に変わる。"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from engine.latin.build import build_glyph
from engine.latin.gate import ink_area
from engine.latin.load import load_resolved
from engine.latin.outline import fit_outline

STYLES = ("modern", "classic", "chic", "pop")
_STRAIGHT = {
    "modern": (15.0, 680.0),
    "classic": (20.0, 620.0),
    "chic": (20.0, 660.0),
    "pop": (120.0, 540.0),
}


def _runs(outline, y: float) -> list[tuple[float, float]]:
    xs: list[float] = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in pairwise(ring + ring[:1]):
            if (start.y - y) * (end.y - y) > 0.0 or abs(end.y - start.y) < 1e-9:
                continue
            t = (y - start.y) / (end.y - start.y)
            if 0.0 <= t < 1.0:
                xs.append(start.x + (end.x - start.x) * t)
    xs.sort()
    return [(xs[index], xs[index + 1]) for index in range(0, len(xs) - 1, 2)]


def _crotch(outline) -> float:
    tip = min(point.y for contour in outline.contours for point in contour)
    for y in range(int(tip) + 2, 680, 2):
        if len(_runs(outline, float(y))) == 2:
            return float(y)
    raise AssertionError("valley never opens")


def _clip(points, y0: float, y1: float):
    def portion(start, end):
        ts = [0.0, 1.0]
        if abs(end.y - start.y) > 1e-9:
            for y in (y0, y1):
                t = (y - start.y) / (end.y - start.y)
                if 0.0 <= t <= 1.0:
                    ts.append(t)
        found = []
        for left, right in pairwise(sorted(set(ts))):
            mid = start.y + (end.y - start.y) * (left + right) / 2.0
            if y0 - 1e-6 <= mid <= y1 + 1e-6:
                found = [
                    start + (end - start) * left,
                    start + (end - start) * right,
                ]
        return found

    chains: list[list] = []
    current: list = []
    ring = list(points)
    for start, end in pairwise(ring + ring[:1]):
        segment = portion(start, end)
        if not segment:
            if current:
                chains.append(current)
                current = []
            continue
        if current and (current[-1] - segment[0]).length() < 0.05:
            current.append(segment[-1])
        else:
            if current:
                chains.append(current)
            current = list(segment)
    if current:
        chains.append(current)
    split: list[list] = []
    for chain in chains:
        piece = [chain[0]]
        for index in range(1, len(chain) - 1):
            prev, point, nxt = chain[index - 1], chain[index], chain[index + 1]
            piece.append(point)
            d1, d2 = point - prev, nxt - point
            if d1.length() > 0.5 and d2.length() > 0.5:
                turn = abs(math.degrees(math.atan2(d1.cross(d2), d1.dot(d2))))
                if turn > 20.0:
                    split.append(piece)
                    piece = [point]
        piece.append(chain[-1])
        split.append(piece)
    return split


def _deviation(chain) -> float:
    start, end = chain[0], chain[-1]
    length = (end - start).length()
    if length < 1.0 or len(chain) < 3:
        return 0.0
    return max(abs((point - start).cross(end - start)) / length for point in chain[1:-1])


@pytest.mark.parametrize("style", STYLES)
def test_leg_edges_are_straight(style):
    """脚の直線部分は端点を結ぶ線から 0.5 UPM 以上ずれない。"""
    outline = build_glyph(load_resolved("V", style))
    y0, y1 = _STRAIGHT[style]
    long = []
    for chain in _clip(outline.contours[0], y0, y1):
        if (chain[-1] - chain[0]).length() < 80.0:
            continue
        long.append(chain)
        assert _deviation(chain) <= 0.5
    assert len(long) == 4


def test_modern_v_fits_as_seven_lines():
    resolved = load_resolved("V", "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert len(paths) == 1
    assert [segment[0] for segment in paths[0].segs] == ["L"] * 7


@pytest.mark.parametrize("style", ("modern", "classic", "chic"))
def test_flat_tip_has_the_style_width(style):
    resolved = load_resolved("V", style)
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    want = resolved.style.metrics["apex_flat"] * resolved.style.pen.stem * cap
    points = [point for contour in outline.contours for point in contour]
    ymin = min(point.y for point in points)
    flat = [point for point in points if point.y < ymin + 0.8]
    assert max(point.y for point in flat) - ymin < 0.5
    assert max(point.x for point in flat) - min(point.x for point in flat) == pytest.approx(want, abs=1.0)


def test_pop_tip_is_the_style_circle():
    resolved = load_resolved("V", "pop")
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    radius = resolved.style.metrics["apex_round"] * resolved.style.pen.stem * cap
    ymin = min(point.y for contour in outline.contours for point in contour)
    dy = 20.0
    width = _runs(outline, ymin + dy)[0]
    chord = width[1] - width[0]
    circle = 2.0 * math.sqrt(2.0 * radius * dy - dy * dy)
    assert chord == pytest.approx(circle, abs=1.0)


@pytest.mark.parametrize("style", STYLES)
def test_leg_width_tapers_along_the_whole_leg(style):
    """太さは足で 1、先端で apex_taper。途中は一次。股より上だけで測る。"""
    resolved = load_resolved("V", style)
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    tip = -resolved.style.overshoot["apex"] * cap
    taper = resolved.style.metrics["apex_taper"]
    crotch = _crotch(outline)
    samples = [y for y in (0.25 * cap, 0.75 * cap) if y > crotch + 8.0]
    if len(samples) < 2:
        samples = [crotch + 80.0, 0.75 * cap]

    def factor(y: float) -> float:
        return taper + (1.0 - taper) * (y - tip) / (cap - tip)

    widths = []
    for y in samples:
        runs = _runs(outline, y)
        assert len(runs) == 2
        widths.append([run[1] - run[0] for run in runs])
    for index in (0, 1):
        ratio = widths[0][index] / widths[1][index]
        expect = factor(samples[0]) / factor(samples[1])
        assert ratio == pytest.approx(expect, rel=0.02)


@pytest.mark.parametrize("style", STYLES)
def test_valley_stays_open_above_the_crotch(style):
    resolved = load_resolved("V", style)
    outline = build_glyph(resolved)
    stem = resolved.style.pen.stem * resolved.style.cap_height
    crotch = _crotch(outline)
    runs = _runs(outline, crotch + 70.0)
    assert len(runs) == 2
    gap = runs[1][0] - runs[0][1]
    floor = 0.30 if style == "chic" else 0.35
    assert gap >= floor * stem


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_diagonal_serifs_are_square(style):
    """下面は水平、両端は垂直。シックは下面の直下に楔を足さない。"""
    resolved = load_resolved("V", style)
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    thick = max(resolved.style.metrics["serif_thick"] * cap, 1.0)
    underside = cap - thick
    points = list(outline.contours[0])
    ends = 0
    for start, end in pairwise(points + points[:1]):
        if abs(start.x - end.x) > 0.5 or abs(max(start.y, end.y) - cap) > 0.5:
            continue
        if abs(start.y - end.y) < thick * 0.5:
            continue
        assert min(start.y, end.y) == pytest.approx(underside, abs=0.5)
        ends += 1
    assert ends == 4
    if style == "chic":
        tucked = [point for point in points if underside - 1.0 < point.y < underside - 0.15]
        assert tucked == []


def test_classic_brackets_have_no_corner():
    resolved = load_resolved("V", "classic")
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    thick = resolved.style.metrics["serif_thick"] * cap
    reach = resolved.style.metrics["bracket"] * cap
    underside = cap - thick
    points = list(outline.contours[0])
    seen = 0
    for index, point in enumerate(points):
        if not underside - reach - 4.0 < point.y < underside + 0.4:
            continue
        prev, nxt = points[index - 1], points[(index + 1) % len(points)]
        d1, d2 = point - prev, nxt - point
        if d1.length() < 0.4 or d2.length() < 0.4:
            continue
        turn = abs(math.degrees(math.atan2(d1.cross(d2), d1.dot(d2))))
        if turn > 40.0:
            continue
        seen += 1
        assert turn <= 5.0
    assert seen > 8


@pytest.mark.parametrize("style", STYLES)
def test_v_ink_stays_in_the_provisional_band(style):
    """モダン・クラシック・ポップは 0.70–0.80。シックは参照書体を見るまで帯を分けて記録する。"""
    v_ink = ink_area(build_glyph(load_resolved("V", style)))
    h_ink = ink_area(build_glyph(load_resolved("H", style)))
    ratio = v_ink / h_ink
    if style == "chic":
        assert 0.55 < ratio < 0.75
    else:
        assert 0.70 <= ratio <= 0.80
