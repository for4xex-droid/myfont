"""クラシックとシックの B。穴は凸、中央の横棒は天地と同じ太さ。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from engine.latin import build
from engine.latin.build import build_glyph
from engine.latin.load import load_resolved

_FIXTURE = Path(__file__).parent / "fixtures" / "latin_unchanged_outlines.json"
_CONTRAST = ("classic", "chic")
_UNCHANGED = (
    ("B", "modern"),
    ("B", "pop"),
    ("H", "classic"),
    ("H", "chic"),
    ("O", "classic"),
    ("O", "chic"),
    ("V", "classic"),
    ("V", "chic"),
    ("S", "classic"),
    ("S", "chic"),
    ("zero", "classic"),
    ("zero", "chic"),
)


def _ring(contour):
    pts = list(contour)
    if len(pts) > 1 and abs(pts[0].x - pts[-1].x) < 1e-6 and abs(pts[0].y - pts[-1].y) < 1e-6:
        pts = pts[:-1]
    return pts


def _resample(pts, step):
    out = [pts[0]]
    carry = 0.0
    for start, end in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(end.x - start.x, end.y - start.y)
        if length < 1e-9:
            continue
        t = step - carry
        while t <= length:
            out.append(type(start)(start.x + (end.x - start.x) * t / length, start.y + (end.y - start.y) * t / length))
            t += step
        carry = length - (t - step)
    return out[:-1]


def _curvature(pts):
    """度/10単位。±2点（6単位）の進行方向の変化。"""
    found = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[(i - 2) % n], pts[i], pts[(i + 2) % n]
        turn = math.atan2(c.y - b.y, c.x - b.x) - math.atan2(b.y - a.y, b.x - a.x)
        turn = (turn + math.pi) % (2 * math.pi) - math.pi
        found.append(math.degrees(turn) / 6.0 * 10.0)
    return found


def _stem_right(resolved) -> float:
    cap = resolved.style.cap_height
    width = resolved.style.proportions["B"] * cap
    left = resolved.style.sidebearing["base"] * cap * resolved.style.sidebearing["straight"]
    return left + 0.18 * width + cap * resolved.pen.stem / 2.0


def _holes(outline):
    return [contour for contour, hole in zip(outline.contours, outline.holes) if hole]


def _outer(outline):
    return next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)


def _dent(contour) -> float:
    """凸包からのへこみ。点が包の辺から何単位内側か。"""
    pts = _ring(contour)
    unique = sorted({(round(p.x, 4), round(p.y, 4)) for p in pts})

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return 0.0

    def distance(px, py):
        best = 1e9
        for a, b in zip(hull, hull[1:] + hull[:1]):
            abx, aby = b[0] - a[0], b[1] - a[1]
            length = abx * abx + aby * aby
            t = 0.0 if length < 1e-12 else max(0.0, min(1.0, ((px - a[0]) * abx + (py - a[1]) * aby) / length))
            best = min(best, math.hypot(px - a[0] - abx * t, py - a[1] - aby * t))
        return best

    return max(distance(p.x, p.y) for p in pts)


def _right_of_stem(contour, stem_right):
    pts = _resample(_ring(contour), 3.0)
    kept = [i for i, point in enumerate(pts) if point.x >= stem_right + 25.0]
    curve = _curvature(pts)
    return pts, curve, kept


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_counters_stay_convex(style):
    """穴が凸からへこむと、肩や波に見える。"""
    outline = build_glyph(load_resolved("B", style))
    dents = [_dent(hole) for hole in _holes(outline)]
    assert dents
    assert max(dents) <= 0.3


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_counters_do_not_reverse(style):
    """穴の右側で、曲がりが逆向きになると縁が波打つ。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    worst = 0.0
    for hole in _holes(outline):
        _pts, curve, kept = _right_of_stem(hole, _stem_right(resolved))
        sign = 1.0 if sum(curve) > 0.0 else -1.0
        if kept:
            worst = max(worst, max(0.0, max(-sign * curve[i] for i in kept)))
    assert worst <= 0.05


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_counter_curvature_does_not_jump(style):
    """平らな所から曲がりへ、曲率が段にならない。幹との直角は除く。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    worst = 0.0
    for hole in _holes(outline):
        _pts, curve, kept = _right_of_stem(hole, _stem_right(resolved))
        for i in kept:
            worst = max(worst, abs(curve[(i + 3) % len(curve)] - curve[i]))
    assert worst <= 6.0


def _bars(outline, stem_right):
    """平らな横棒の（下、中央、上）の太さ。セリフで太った所は除く。"""

    def crossings(contour, x):
        pts = _ring(contour)
        found = []
        for start, end in zip(pts, pts[1:] + pts[:1]):
            if (start.x <= x < end.x) or (end.x <= x < start.x):
                t = (x - start.x) / (end.x - start.x)
                found.append(start.y + t * (end.y - start.y))
        return found

    samples = []
    x = stem_right + 10.0
    limit = max(point.x for contour in outline.contours for point in contour) - 10.0
    while x < limit:
        ys = sorted(y for contour in outline.contours for y in crossings(contour, x))
        if len(ys) == 6:
            samples.append((ys[1] - ys[0], ys[3] - ys[2], ys[5] - ys[4]))
        x += 8.0
    assert samples
    tops = sorted(top for _bottom, _mid, top in samples)
    cut = tops[max(0, len(tops) // 5)]
    band = [row for row in samples if row[2] <= cut + 1.5]
    assert band
    n = len(band)
    return band[n // 2]


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_middle_bar_matches_the_others(style):
    """中央の横棒は、天地の横棒の ±10%。"""
    resolved = load_resolved("B", style)
    bottom, middle, top = _bars(build_glyph(resolved), _stem_right(resolved))
    assert middle == pytest.approx(top, rel=0.10)
    assert middle == pytest.approx(bottom, rel=0.10)


def _wall(hole, outer):
    """穴の右側で、外の輪郭がさらに右にある点と、その画の太さ。"""
    pts = _ring(hole)
    edge = _ring(outer)
    left = min(point.x for point in pts)
    right = max(point.x for point in pts)
    found = []
    for point in _resample(pts, 6.0):
        if point.x <= left + 0.72 * (right - left):
            continue
        best = 1e9
        nearest_x = point.x
        for start, end in zip(edge, edge[1:] + edge[:1]):
            abx, aby = end.x - start.x, end.y - start.y
            length = abx * abx + aby * aby
            t = 0.0 if length < 1e-12 else max(0.0, min(1.0, ((point.x - start.x) * abx + (point.y - start.y) * aby) / length))
            qx = start.x + abx * t
            qy = start.y + aby * t
            dist = math.hypot(point.x - qx, point.y - qy)
            if dist < best:
                best = dist
                nearest_x = qx
        if nearest_x >= point.x - 2.0:
            found.append((point, best))
    return found


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_thickest_matches_the_stem(style):
    """山の一番太い所は、ステムの ±3%。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    outer = _outer(outline)
    stem = resolved.pen.stem * resolved.style.cap_height
    for hole in _holes(outline):
        thick = [dist for _point, dist in _wall(hole, outer)]
        assert thick
        assert max(thick) == pytest.approx(stem, rel=0.03)


def test_chic_b_cap_and_baseline_are_hairlines():
    """天地の横棒は、ヘアラインの2倍まで。"""
    resolved = load_resolved("B", "chic")
    bottom, _middle, top = _bars(build_glyph(resolved), _stem_right(resolved))
    hairline = resolved.pen.hairline * resolved.style.cap_height
    assert top <= hairline * 2.0
    assert bottom <= hairline * 2.0


def _bow_curvature(style):
    """穴の右側。平らな横画と幹の角は除く。"""
    resolved = load_resolved("B", style)
    outline = build_glyph(resolved)
    stem = _stem_right(resolved)
    found = []
    for hole in _holes(outline):
        pts = _resample(_ring(hole), 3.0)
        curve = _curvature(pts)
        side = [(point, abs(kappa)) for point, kappa in zip(pts, curve) if point.x > stem + 80.0 and abs(kappa) > 0.4]
        found.append(side)
    return found


def test_bowl_curvature_follows_the_pen():
    """細い方向で曲がりが強く、太い方向では開く。半円の一定曲率には戻さない。"""
    for side in _bow_curvature("classic"):
        ys = [point.y for point, _kappa in side]
        mid = (min(ys) + max(ys)) / 2.0
        lower = [kappa for point, kappa in side if point.y < mid]
        upper = [kappa for point, kappa in side if point.y >= mid]
        assert sum(lower) / len(lower) > sum(upper) / len(upper)
    for side in _bow_curvature("chic"):
        ys = [point.y for point, _kappa in side]
        low, high = min(ys), max(ys)
        span = high - low
        middle = [kappa for point, kappa in side if abs(point.y - (low + high) / 2.0) < span * 0.2]
        ends = [kappa for point, kappa in side if abs(point.y - (low + high) / 2.0) > span * 0.35]
        assert sum(ends) / len(ends) > sum(middle) / len(middle) * 1.8


def test_classic_b_outer_hills_are_not_notched():
    """右側の太さが段になると、山の外側が欠けて見える。"""
    pts = _ring(_outer(build_glyph(load_resolved("B", "classic"))))
    count = len(pts)
    right = max(point.x for point in pts)
    for index, point in enumerate(pts):
        if point.x < right - 40.0:
            continue
        before, after = pts[(index - 1) % count], pts[(index + 1) % count]
        turn = math.atan2(after.y - point.y, after.x - point.x) - math.atan2(point.y - before.y, point.x - before.x)
        turn = (turn + math.pi) % (2 * math.pi) - math.pi
        assert abs(math.degrees(turn)) < 8.0


def test_classic_b_stress_follows_the_pen():
    """太い所は右上、細い所は右下。上下の山で最太と最細は ±8%。"""
    outline = build_glyph(load_resolved("B", "classic"))
    outer = _outer(outline)
    maxima = []
    minima = []
    for hole in _holes(outline):
        wall = _wall(hole, outer)
        assert wall
        mid = (min(point.y for point, _dist in wall) + max(point.y for point, _dist in wall)) / 2.0
        upper = sorted(dist for point, dist in wall if point.y >= mid)
        lower = sorted(dist for point, dist in wall if point.y < mid)
        assert upper and lower
        assert upper[len(upper) // 2] > lower[len(lower) // 2] * 1.05
        thick = sorted(dist for _point, dist in wall)
        maxima.append(thick[-1])
        minima.append(thick[0])
    assert abs(maxima[0] - maxima[1]) / max(maxima) <= 0.08
    assert abs(minima[0] - minima[1]) / max(minima) <= 0.08


def _valley(outer):
    pts = _ring(outer)
    ys = [point.y for point in pts]
    mid = (min(ys) + max(ys)) / 2.0
    span = max(ys) - min(ys)
    right = max(point.x for point in pts)
    band = [point for point in pts if abs(point.y - mid) < 0.22 * span and point.x > right - 160.0]
    assert band
    return min(band, key=lambda point: point.x)


def _valley_gap(hole, valley):
    return min(math.hypot(point.x - valley.x, point.y - valley.y) for point in _ring(hole))


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_waist_gaps_match(style):
    """外の谷から上下の穴までの距離が ±10% で揃う。"""
    outline = build_glyph(load_resolved("B", style))
    valley = _valley(_outer(outline))
    gaps = sorted(_valley_gap(hole, valley) for hole in _holes(outline))
    assert gaps[1] - gaps[0] <= 0.10 * gaps[1]


def _hausdorff(left, right) -> float:
    def directed(src, dst):
        worst = 0.0
        n = len(dst)
        for px, py in src:
            near = 1e9
            for i in range(n):
                ax, ay = dst[i]
                bx, by = dst[(i + 1) % n]
                abx, aby = bx - ax, by - ay
                length = abx * abx + aby * aby
                t = 0.0 if length < 1e-12 else max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / length))
                near = min(near, math.hypot(px - ax - abx * t, py - ay - aby * t))
            worst = max(worst, near)
        return worst

    return max(directed(left, right), directed(right, left))


def _outline_gap(left, right) -> float:
    used: set[int] = set()
    worst = 0.0
    for contour in left.contours:
        points = [(point.x, point.y) for point in contour]
        index = min(
            (i for i in range(len(right.contours)) if i not in used),
            key=lambda i: _hausdorff(points, [(point.x, point.y) for point in right.contours[i]]),
        )
        used.add(index)
        worst = max(worst, _hausdorff(points, [(point.x, point.y) for point in right.contours[index]]))
    return worst


@pytest.mark.parametrize("style", _CONTRAST)
def test_contrast_b_ignores_hug_and_sample_count(style):
    """この2字の輪郭は、抱き込みと横棒の角丸めを通らない。サンプル 24 と 160 の差は 0.6 以内。"""
    resolved = load_resolved("B", style)
    base = build_glyph(resolved)

    def no_hug(samples, widths, bar_half):
        return samples, widths

    def no_fair(points, *, mid_y):
        return points

    original_hug, original_fair = build._hug_outer, build.fair_bar_joins
    build._hug_outer, build.fair_bar_joins = no_hug, no_fair
    try:
        assert _outline_gap(base, build_glyph(resolved)) <= 0.05
    finally:
        build._hug_outer, build.fair_bar_joins = original_hug, original_fair

    original_samples = build._SAMPLES
    try:
        for count in (24, 160):
            build._SAMPLES = count
            assert _outline_gap(base, build_glyph(resolved)) <= 0.6
    finally:
        build._SAMPLES = original_samples


@pytest.mark.parametrize(("glyph", "style"), _UNCHANGED)
def test_other_glyphs_keep_their_outline(glyph, style):
    """クラシックとシックの B 以外のパイロット字は、輪郭を動かさない。"""
    saved = json.loads(_FIXTURE.read_text())[f"{style}/{glyph}"]
    outline = build_glyph(load_resolved(glyph, style))
    assert outline.contour_count == len(saved["contours"])
    used = set()
    for contour, hole in zip(outline.contours, outline.holes):
        points = [(point.x, point.y) for point in contour]
        best_i = min(
            (i for i in range(len(saved["contours"])) if i not in used),
            key=lambda i: _hausdorff(points, saved["contours"][i]),
        )
        assert _hausdorff(points, saved["contours"][best_i]) <= 0.05
        assert bool(hole) is saved["holes"][best_i]
        used.add(best_i)
