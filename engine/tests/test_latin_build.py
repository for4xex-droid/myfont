"""パイロット6字が様式ごとに輪郭を返す。"""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise

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


def _tip_rise(style: str, *, band: float = 12.0) -> float:
    outer = build_glyph(load_resolved("V", style)).contours[0]
    ymin = min(point.y for point in outer)
    low = [point for point in outer if point.y < ymin + band]
    return max(point.y for point in low) - ymin


def test_modern_v_tip_has_no_valley():
    assert _tip_rise("modern") < 4


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_v_tip_is_level(style):
    """切り口そのものが水平。脚の最初の点は切り口ではない。"""
    assert _tip_rise(style, band=2.0) < 1.0


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_v_tip_has_no_side_stub(style):
    outer = build_glyph(load_resolved("V", style)).contours[0]
    ymin = min(point.y for point in outer)
    flat = [point for point in outer if point.y < ymin + 2]
    right = max(point.x for point in flat)
    stub = [point for point in outer if ymin + 2 <= point.y < ymin + 40 and point.x > right + 18]
    assert stub == []


@pytest.mark.parametrize("glyph", ("O", "zero"))
def test_chic_bowl_crown_is_not_a_corner(glyph):
    """幅の式が最細で折れると、天地の内周が角になる。"""
    outline = build_glyph(load_resolved(glyph, "chic"))
    hole = next(contour for contour, is_hole in zip(outline.contours, outline.holes) if is_hole)
    assert min(_turns(hole)) > -20.0


@pytest.mark.parametrize("style", STYLES)
def test_round_o_bottom_stays_curved(style):
    outline = build_glyph(load_resolved("O", style))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    ymin = min(point.y for point in outer)
    low = [point for point in outer if point.y < ymin + 8]
    assert max(point.y for point in low) - ymin > 2


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_b_bowl_stays_with_the_foot(style):
    outline = build_glyph(load_resolved("B", style))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    left = min(point.x for point in outer)
    foot = [point for point in outer if point.x < left + 70 and point.y < 80]
    bottom = min(point.y for point in foot)
    near = [point for point in outer if point.x < left + 200 and point.y < 80]
    assert min(point.y for point in near) > bottom - 12
    notch = [point for point in outer if left + 80 < point.x < left + 160 and bottom + 1 < point.y < 30]
    assert notch == []


def _ys(outline):
    return [point.y for contour in outline.contours for point in contour]


@pytest.mark.parametrize("style", STYLES)
def test_pilot_sits_on_the_lines(style):
    cap = 700.0
    for glyph in ("H", "V"):
        ys = _ys(build_glyph(load_resolved(glyph, style)))
        assert max(ys) == pytest.approx(cap, abs=0.5)
    assert min(_ys(build_glyph(load_resolved("H", style)))) == pytest.approx(0.0, abs=0.5)
    resolved = load_resolved("V", style)
    apex = resolved.style.overshoot["apex"] * cap
    assert min(_ys(build_glyph(resolved))) == pytest.approx(-apex, abs=1.0)
    for glyph in ("O", "S", "zero"):
        resolved = load_resolved(glyph, style)
        over = resolved.style.overshoot["round"] * cap
        ys = _ys(build_glyph(resolved))
        assert min(ys) == pytest.approx(-over, abs=0.5)
        assert max(ys) == pytest.approx(cap + over, abs=0.5)
    resolved = load_resolved("B", style)
    over = resolved.style.overshoot["round"] * cap
    ys = _ys(build_glyph(resolved))
    assert any(abs(y) < 0.5 for y in ys) and any(abs(y - cap) < 0.5 for y in ys)
    assert min(ys) >= -over and max(ys) <= cap + over


def _unimodal(profile):
    peak = max(range(len(profile)), key=lambda i: profile[i][1])
    rising = all(b[1] >= a[1] - 0.5 for a, b in pairwise(profile[: peak + 1]))
    falling = all(b[1] <= a[1] + 0.5 for a, b in pairwise(profile[peak:]))
    return rising and falling


@pytest.mark.parametrize("style", STYLES)
def test_s_crown_has_no_saddle(style):
    outer = build_glyph(load_resolved("S", style)).contours[0]
    top = max(point.y for point in outer)
    bottom = min(point.y for point in outer)
    crown = sorted((point.x, point.y) for point in outer if point.y > top - 16)
    base = sorted((point.x, -point.y) for point in outer if point.y < bottom + 16)
    assert _unimodal(crown)
    assert _unimodal(base)


def test_pop_v_apex_is_one_round():
    outer = build_glyph(load_resolved("V", "pop")).contours[0]
    ymin = min(point.y for point in outer)
    low = sorted((point.x, -point.y) for point in outer if point.y < ymin + 20)
    assert _unimodal(low)


@pytest.mark.parametrize("style", ("modern", "classic", "chic"))
def test_b_top_is_flat_past_the_stem(style):
    """上下の直線が幹の内側で終わると、外へ出た瞬間に天が傾く。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    cap = resolved.style.cap_height
    width = resolved.style.proportions["B"] * cap
    left = resolved.style.sidebearing["base"] * cap * resolved.style.sidebearing["straight"]
    stem_right = left + 0.18 * width + cap * resolved.pen.stem / 2.0
    top = max(point.y for point in outer)
    flat = [point.x for point in outer if point.y > top - 1.5]
    assert max(flat) > stem_right + 0.08 * width


def _bar_join_fault(contour, cap: float) -> tuple[float, float, bool]:
    """中央の横棒の右端から碗へ入る最初の角（水平からの度）と、横棒側への凹み。"""
    import math

    pts = list(contour)
    if len(pts) > 1 and pts[0].x == pts[-1].x and pts[0].y == pts[-1].y:
        pts = pts[:-1]
    n = len(pts)
    best: tuple[float, int, object, object] | None = None
    for index in range(n):
        start, end = pts[index], pts[(index + 1) % n]
        if abs(end.x - start.x) < 40.0 or abs(end.y - start.y) > 1.2:
            continue
        y = (start.y + end.y) / 2.0
        score = abs(y - cap / 2.0)
        if best is None or score < best[0]:
            best = (score, index, start, end)
    assert best is not None
    _score, index, start, end = best
    if end.x >= start.x:
        junction, step, origin = (index + 1) % n, 1, end
    else:
        junction, step, origin = index, -1, start
    nxt = pts[(junction + step) % n]
    delta = nxt - origin
    off = abs(math.degrees(math.atan2(delta.y, delta.x)))
    depart = min(off, 180.0 - off)
    walked = 0.0
    cursor = junction
    seen = [origin]
    far = origin
    while walked < 80.0:
        nxt = pts[(cursor + step) % n]
        walked += (nxt - pts[cursor]).length()
        cursor = (cursor + step) % n
        seen.append(pts[cursor])
        if walked >= 36.0 and far is origin:
            far = pts[cursor]
    if far.y >= origin.y:
        dip = origin.y - min(point.y for point in seen)
    else:
        dip = max(point.y for point in seen) - origin.y
    signs = []
    for index in range(1, len(seen) - 1):
        bend = _turns([seen[index - 1], seen[index], seen[index + 1]])[1]
        if abs(bend) > 4.0:
            signs.append(1 if bend > 0.0 else -1)
    flipped = any(left != right for left, right in pairwise(signs))
    return depart, dip, flipped


@pytest.mark.parametrize("style", STYLES)
def test_b_bar_meets_the_bowl_without_a_kink(style):
    """横棒の太さが碗の入り口で急に変わると、内周が凹むか角になる。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    faults = [
        _bar_join_fault(contour, resolved.style.cap_height)
        for contour, hole in zip(outline.contours, outline.holes)
        if hole
    ]
    assert len(faults) == 2
    for depart, dip, flipped in faults:
        assert depart < 12.0
        assert dip < 3.0
        assert not flipped


def _floor_dip(contour) -> float:
    """下の碗が地の横棒へ入る側で、内周が横棒の線よりどれだけ食い込むか。"""
    pts = list(contour)
    if len(pts) > 1 and pts[0].x == pts[-1].x and pts[0].y == pts[-1].y:
        pts = pts[:-1]
    n = len(pts)
    floors = []
    for index in range(n):
        start, end = pts[index], pts[(index + 1) % n]
        if abs(end.x - start.x) < 40.0 or abs(end.y - start.y) > 1.2:
            continue
        floors.append(((start.y + end.y) / 2.0, index, start, end))
    if not floors:
        return 0.0
    _height, index, start, end = min(floors)
    if end.x >= start.x:
        junction, step, origin = (index + 1) % n, 1, end
    else:
        junction, step, origin = index, -1, start
    walked = 0.0
    cursor = junction
    low = origin.y
    while walked < 120.0:
        nxt = pts[(cursor + step) % n]
        walked += (nxt - pts[cursor]).length()
        cursor = (cursor + step) % n
        low = min(low, pts[cursor].y)
        if pts[cursor].y > origin.y + 50.0:
            break
    return origin.y - low


def test_classic_b_lower_bowl_does_not_gouge_the_baseline():
    """下の山から地の横棒へ入る内周が、横棒の中へえぐれない。"""
    outline = build_glyph(load_resolved("B", "classic"))
    dips = [_floor_dip(contour) for contour, hole in zip(outline.contours, outline.holes) if hole]
    assert dips
    assert max(dips) < 2.0


def _right_extent(contour, y: float) -> float:
    xs = [point.x for point in contour if abs(point.y - y) < 10.0 and point.x > 400.0]
    assert xs
    return max(xs)


def _peak_x(contour, low: float, high: float) -> float:
    best = 0.0
    y = low
    while y <= high:
        xs = [point.x for point in contour if abs(point.y - y) < 10.0 and point.x > 100.0]
        if xs:
            best = max(best, max(xs))
        y += 10.0
    assert best > 0.0
    return best


@pytest.mark.parametrize("style", STYLES)
def test_b_bowls_swell_the_same_way(style):
    """上下の山は、右への出方が揃っていないと別の形に見える。"""
    outline = build_glyph(load_resolved("B", style))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    lower = _peak_x(outer, 100.0, 280.0)
    upper = _peak_x(outer, 480.0, 640.0)
    assert abs(lower - upper) <= 8.0


def test_modern_b_valley_is_sharp():
    """腰の外側の谷が丸いと、二つの山の境が締まらない。内周は動かさない。"""
    outline = build_glyph(load_resolved("B", "modern"))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    crown = _peak_x(outer, 480.0, 640.0)
    waist = min(_right_extent(outer, y) for y in (350.0, 360.0, 370.0))
    assert 55.0 <= crown - waist <= 90.0
    assert min(_turns(outer)) > -60.0
    upper = max(
        (contour for contour, hole in zip(outline.contours, outline.holes) if hole),
        key=lambda contour: max(point.y for point in contour),
    )
    lower = min(
        (contour for contour, hole in zip(outline.contours, outline.holes) if hole),
        key=lambda contour: max(point.y for point in contour),
    )
    assert abs(_peak_x(upper, 480.0, 620.0) - _peak_x(lower, 140.0, 280.0)) <= 8.0


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_serif_b_stays_on_the_cap(style):
    ys = _ys(build_glyph(load_resolved("B", style)))
    assert min(ys) == pytest.approx(0.0, abs=1.0)
    assert max(ys) == pytest.approx(700.0, abs=1.0)


def test_chic_s_inner_crown_is_not_a_spike():
    outer = list(build_glyph(load_resolved("S", "chic")).contours[0])
    if outer[0].x == outer[-1].x and outer[0].y == outer[-1].y:
        outer = outer[:-1]
    ymax = max(point.y for point in outer)
    for index, point in enumerate(outer):
        if not ymax - 40.0 < point.y < ymax - 8.0:
            continue
        prev = outer[index - 1]
        nxt = outer[(index + 1) % len(outer)]
        assert point.y <= max(prev.y, nxt.y) + 3.0


def _horizontal_chords(outline, y: float) -> list[float]:
    outer = list(outline.contours[0])
    xs: list[float] = []
    for index, point in enumerate(outer):
        nxt = outer[(index + 1) % len(outer)]
        if (point.y <= y < nxt.y) or (nxt.y <= y < point.y):
            t = (y - point.y) / (nxt.y - point.y)
            xs.append(point.x + t * (nxt.x - point.x))
    xs.sort()
    return [xs[index + 1] - xs[index] for index in range(0, len(xs) - 1, 2)]


def test_chic_v_right_leg_is_slanted_thin():
    """右脚は幹の 0.40。ヘアラインの針にはしない。平らな切り口で脚は股より下で一つになる。"""
    resolved = load_resolved("V", "chic")
    outline = build_glyph(resolved)
    hairline = resolved.style.pen.hairline * resolved.style.cap_height
    for y in (400.0, 600.0):
        left, right = _horizontal_chords(outline, y)
        assert right == pytest.approx(left * 0.40, rel=0.08)
        assert right > hairline * 3.0
    assert len(_ink_runs(outline, 150.0)) == 1
    assert len(_ink_runs(outline, 400.0)) == 2


def test_classic_v_right_arm_follows_the_pen():
    """右脚はペン角の太さ。ヘアラインより太く、左のステムよりは細い。"""
    resolved = load_resolved("V", "classic")
    outline = build_glyph(resolved)
    left, right = _horizontal_chords(outline, 400.0)
    hairline = resolved.pen.hairline * resolved.style.cap_height
    assert right > hairline * 1.5
    assert right < left * 0.9


def test_modern_b_stem_reaches_the_bowl_ends():
    outline = build_glyph(load_resolved("B", "modern"))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    left = min(point.x for point in outer)
    edge = [point for point in outer if point.x < left + 3]
    top = max(point.y for point in edge)
    bottom = min(point.y for point in edge)
    beside = [point for point in outer if left <= point.x < left + 55]
    assert not any(point.y > top + 8 for point in beside)
    assert not any(point.y < bottom - 8 for point in beside)


def test_modern_b_bowls_do_not_stick_out_of_the_stem():
    """碗が幹の左より外へ出ない。幹の位置は、天地の左端で見る。"""
    outline = build_glyph(load_resolved("B", "modern"))
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    ends = [point for point in outer if point.y <= 2.0 or point.y >= 698.0]
    stem_left = min(point.x for point in ends)
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


def _bar_band(outline) -> tuple[float, float]:
    """字の左右の中央を縦に切った、横棒の下端と上端。"""
    xs = [
        point.x
        for contour, hole in zip(outline.contours, outline.holes)
        if not hole
        for point in contour
    ]
    x = (min(xs) + max(xs)) / 2.0
    ys = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in pairwise(ring + ring[:1]):
            if (start.x - x) * (end.x - x) > 0.0 or abs(end.x - start.x) < 1e-9:
                continue
            t = (x - start.x) / (end.x - start.x)
            if 0.0 <= t < 1.0:
                ys.append(start.y + (end.y - start.y) * t)
    ys.sort()
    assert len(ys) == 2
    return ys[0], ys[1]


@pytest.mark.parametrize("style", STYLES)
def test_h_bar_sits_at_the_style_height(style):
    """横棒の中心は様式の 0.52。上の空きは下の 0.88–0.95 倍。"""
    outline = build_glyph(load_resolved("H", style))
    bottom, top = _bar_band(outline)
    cap = 700.0
    assert (bottom + top) / 2.0 == pytest.approx(0.52 * cap, abs=1.0)
    assert 0.88 <= (cap - top) / bottom <= 0.95
    for y in (150.0, 250.0, 520.0, 620.0):
        assert y < bottom or y > top


def _ink_runs(outline, y: float) -> list[tuple[float, float]]:
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


def test_h_bar_ignores_the_skeleton_height():
    resolved = load_resolved("H", "modern")
    strokes = tuple(
        replace(stroke, knots=tuple(replace(knot, y=0.30) for knot in stroke.knots))
        if stroke.role == "bar"
        else stroke
        for stroke in resolved.skeleton.strokes
    )
    moved = replace(resolved, skeleton=replace(resolved.skeleton, strokes=strokes))
    bottom, top = _bar_band(build_glyph(moved))
    assert (bottom + top) / 2.0 == pytest.approx(0.52 * 700.0, abs=1.0)
