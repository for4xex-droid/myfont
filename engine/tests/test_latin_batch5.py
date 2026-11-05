"""モダンの A と G。他の様式には足さない。"""

from __future__ import annotations

import math
import tempfile
from itertools import pairwise
from pathlib import Path

import pytest

from engine.curve_fit import (
    _polyline_extrema,
    detect_corners,
    hausdorff_path_to_polyline,
)
from engine.latin.build import build_glyph
from engine.latin.compile import build_style, outline_gap
from engine.latin.gate import overshoot_violations
from engine.latin.load import load_resolved, load_style, styles_dir
from engine.latin.outline import fit_outline

_CAP = 700.0
# 横棒の内への長さ。暫定。骨格のコメントと同じ。
_G_INWARD = 200.0


def _resolved(glyph: str):
    return load_resolved(glyph, "modern")


def _built(glyph: str):
    return build_glyph(_resolved(glyph))


def _points(outline):
    return [point for contour in outline.contours for point in contour]


def _ring(contour):
    pts = list(contour)
    if len(pts) > 1 and (pts[0] - pts[-1]).length() < 1e-6:
        return pts[:-1]
    return pts


def _runs(outline, y: float) -> list[tuple[float, float]]:
    xs: list[float] = []
    for contour in outline.contours:
        ring = _ring(contour)
        for start, end in pairwise(ring + ring[:1]):
            if (start.y - y) * (end.y - y) > 0.0 or abs(end.y - start.y) < 1e-9:
                continue
            t = (y - start.y) / (end.y - start.y)
            if 0.0 <= t < 1.0:
                xs.append(start.x + (end.x - start.x) * t)
    xs.sort()
    return [(xs[index], xs[index + 1]) for index in range(0, len(xs) - 1, 2)]


def _deviation(chain) -> float:
    start, end = chain[0], chain[-1]
    length = (end - start).length()
    if length < 1.0 or len(chain) < 3:
        return 0.0
    return max(
        abs((point - start).cross(end - start)) / length for point in chain[1:-1]
    )


def _chains(points, y0: float, y1: float):
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
                found = [start + (end - start) * left, start + (end - start) * right]
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
    return chains


def _valley(outline) -> float:
    tip = max(point.y for point in _points(outline))
    for y in range(int(tip) - 2, 40, -2):
        if len(_runs(outline, float(y))) == 2:
            return float(y)
    raise AssertionError("valley never opens")


def _turns(pts):
    found = []
    for index, point in enumerate(pts):
        prev, nxt = pts[index - 1], pts[(index + 1) % len(pts)]
        d1, d2 = point - prev, nxt - point
        if d1.length() < 0.4 or d2.length() < 0.4:
            continue
        found.append((point, math.degrees(math.atan2(d1.cross(d2), d1.dot(d2)))))
    return found


def _mirror_gap(points) -> float:
    coords = [(point.x, point.y) for point in points]
    mid = (min(x for x, _y in coords) + max(x for x, _y in coords)) / 2.0
    reflected = [(2.0 * mid - x, y) for x, y in coords]

    def directed(left, right) -> float:
        worst = 0.0
        for x, y in left:
            nearest = min(math.hypot(x - u, y - v) for u, v in right)
            worst = max(worst, nearest)
        return worst

    return max(directed(coords, reflected), directed(reflected, coords))


def _pins(contour, corner_deg: float) -> int:
    pts = [(point.x, point.y) for point in _ring(contour)]
    found = set(detect_corners(pts, angle_deg=corner_deg, min_sep_upm=10.0))
    found.update(_polyline_extrema(pts))
    return len(found)


def test_other_styles_do_not_define_a_or_g():
    for name in ("classic", "chic", "pop"):
        style = load_style(styles_dir() / f"{name}.yaml")
        assert "A" not in style.proportions
        assert "G" not in style.proportions


def test_a_top_is_a_narrow_flat():
    resolved = _resolved("A")
    outline = _built("A")
    cap = resolved.style.cap_height
    peak = cap + resolved.style.overshoot["apex"] * cap
    want = resolved.style.metrics["apex_flat"] * resolved.style.pen.stem * cap
    points = _points(outline)
    ymax = max(point.y for point in points)
    assert ymax == pytest.approx(peak, abs=1.0)
    flat = [point for point in points if point.y > ymax - 0.8]
    width = max(point.x for point in flat) - min(point.x for point in flat)
    assert width == pytest.approx(want, abs=2.0)
    assert max(point.y for point in flat) - min(point.y for point in flat) < 0.5


def test_a_feet_sit_on_the_baseline():
    points = _points(_built("A"))
    ymin = min(point.y for point in points)
    assert ymin == pytest.approx(0.0, abs=1.0)
    feet = [point for point in points if point.y < ymin + 0.8]
    assert max(point.y for point in feet) - ymin < 0.5


def test_a_leg_edges_are_straight():
    """横棒より上の脚の縁は直線。横棒のところで脚は一つにつながる。"""
    outline = _built("A")
    valley = _valley(outline)
    bar_top = (
        0.22 * _CAP
        + _resolved("A").pen.bar_ratio * _resolved("A").style.pen.stem * _CAP / 2.0
    )
    long = []
    for contour in outline.contours:
        for chain in _chains(contour, bar_top + 15.0, valley - 12.0):
            if (chain[-1] - chain[0]).length() < 80.0:
                continue
            long.append(chain)
            assert _deviation(chain) <= 0.5
    assert len(long) == 4


def test_a_taper_follows_the_leg_formula():
    resolved = _resolved("A")
    outline = _built("A")
    cap = resolved.style.cap_height
    peak = cap + resolved.style.overshoot["apex"] * cap
    taper = resolved.style.metrics["apex_taper"]

    def factor(y: float) -> float:
        return taper + (1.0 - taper) * (peak - y) / peak

    # 0.25 キャップは横棒の中なので、横棒の上で測った直線の縁をそこまで延ばす。
    valley = _valley(outline)
    bar_top = 0.22 * cap + resolved.pen.bar_ratio * resolved.style.pen.stem * cap / 2.0
    edges = []
    for contour in outline.contours:
        for chain in _chains(contour, bar_top + 15.0, valley - 12.0):
            if (chain[-1] - chain[0]).length() < 80.0:
                continue
            edges.append(chain)
    assert len(edges) == 4

    def at(chain, y: float) -> float:
        start, end = chain[0], chain[-1]
        t = (y - start.y) / (end.y - start.y)
        return (start + (end - start) * t).x

    samples = (0.25 * cap, 0.75 * cap)
    widths = []
    for y in samples:
        xs = sorted(at(chain, y) for chain in edges)
        assert len(xs) == 4
        widths.append([xs[1] - xs[0], xs[3] - xs[2]])
    for index in (0, 1):
        ratio = widths[0][index] / widths[1][index]
        assert ratio == pytest.approx(factor(samples[0]) / factor(samples[1]), rel=0.02)


def test_a_crossbar_keeps_the_skeleton_height():
    resolved = _resolved("A")
    outline = _built("A")
    cap = resolved.style.cap_height
    stem = resolved.style.pen.stem * cap
    want = resolved.pen.bar_ratio * stem
    center = 0.22 * cap
    horizontals = []
    for contour in outline.contours:
        ring = _ring(contour)
        for start, end in pairwise(ring + ring[:1]):
            if abs(end.y - start.y) > 0.4 or abs(end.x - start.x) < 40.0:
                continue
            mid = (start.y + end.y) / 2.0
            if abs(mid - center) > want:
                continue
            horizontals.append(mid)
    assert horizontals
    top, bottom = max(horizontals), min(horizontals)
    assert top - bottom == pytest.approx(want, abs=1.0)
    assert (top + bottom) / 2.0 == pytest.approx(center, abs=1.0)
    peak = cap + resolved.style.overshoot["apex"] * cap
    for contour in outline.contours:
        ring = _ring(contour)
        sign = (
            1.0
            if sum(
                ring[i].x * ring[(i + 1) % len(ring)].y
                - ring[(i + 1) % len(ring)].x * ring[i].y
                for i in range(len(ring))
            )
            > 0.0
            else -1.0
        )
        mild = []
        for point, turn in _turns(ring):
            if not (1.0 < abs(turn) < 70.0 and turn * sign < 0.0):
                continue
            if abs(point.y - peak) <= 1.5 or abs(point.y) <= 1.5:
                continue
            mild.append((round(point.x, 1), round(point.y, 1), round(turn, 1)))
        assert mild == []


def test_a_is_one_symmetric_contour():
    resolved = _resolved("A")
    outline = _built("A")
    assert sum(not hole for hole in outline.holes) == 1
    assert outline.hole_count == 1
    assert _mirror_gap(_points(outline)) <= 1.0
    assert overshoot_violations(outline, resolved) == []


def test_g_is_one_contour_with_a_round_bottom():
    resolved = _resolved("G")
    outline = _built("G")
    assert outline.contour_count == 1
    assert outline.hole_count == 0
    floor = -resolved.style.overshoot["round"] * resolved.style.cap_height
    assert min(point.y for point in _points(outline)) == pytest.approx(floor, abs=1.0)
    assert overshoot_violations(outline, resolved) == []


def test_g_bar_meets_the_circle_and_runs_inward():
    """外角は円の上。左端は中心線から暫定の長さだけ内。太さは幹。"""
    from engine.latin.build import _fit_bowls

    resolved = _resolved("G")
    outline = _built("G")
    cap = resolved.style.cap_height
    stem = resolved.style.pen.stem * cap
    center_y = float(resolved.style.metrics["bar_y"]) * cap
    frame = _fit_bowls(resolved)[0]["bowl"]
    half = stem / 2.0
    cy = (center_y - frame.y_off) / frame.y_scale
    cx = 0.5 + math.sqrt(max(0.0, 0.25 - (cy - 0.5) ** 2))
    centerline_x = frame.x_off + cx * frame.x_scale
    points = _points(outline)
    equator = frame.y_off + 0.5 * frame.y_scale
    right = max(point.x for point in points if abs(point.y - equator) < 40.0)
    seat = right - (frame.x_off + frame.x_scale + half)
    ring = _ring(outline.contours[0])
    horizontals = [
        (start, end)
        for start, end in pairwise(ring + ring[:1])
        if abs(end.y - start.y) < 0.4 and abs(end.x - start.x) > 40.0
    ]
    upper = [
        pair
        for pair in horizontals
        if abs((pair[0].y + pair[1].y) / 2.0 - (center_y + half)) < 1.5
    ]
    lower = [
        pair
        for pair in horizontals
        if abs((pair[0].y + pair[1].y) / 2.0 - (center_y - half)) < 1.5
    ]
    assert upper and lower
    bar_top = max(upper, key=lambda pair: abs(pair[1].x - pair[0].x))
    bar_bottom = max(lower, key=lambda pair: abs(pair[1].x - pair[0].x))
    left = min(bar_top[0].x, bar_top[1].x)
    top_y = (bar_top[0].y + bar_top[1].y) / 2.0
    bottom_y = (bar_bottom[0].y + bar_bottom[1].y) / 2.0
    assert left == pytest.approx(centerline_x + seat - _G_INWARD, abs=1.5)
    assert top_y - bottom_y == pytest.approx(stem, abs=1.0)
    assert (top_y + bottom_y) / 2.0 == pytest.approx(center_y, abs=1.0)


def test_g_stays_inside_the_source_circle():
    from engine.latin.build import _fit_bowls

    resolved = _resolved("G")
    outline = _built("G")
    frame = _fit_bowls(resolved)[0]["bowl"]
    half = resolved.style.pen.stem * resolved.style.cap_height / 2.0
    center_x = frame.x_off + 0.5 * frame.x_scale
    center_y = frame.y_off + 0.5 * frame.y_scale
    points = _points(outline)
    # 着席で枠が平行移動する。円の右端と外形の右端を合わせる。
    right = max(point.x for point in points if abs(point.y - center_y) < 40.0)
    seat = right - (frame.x_off + frame.x_scale + half)
    worst = 0.0
    for point in points:
        qx, qy = point.x - seat, point.y
        theta = math.atan2(
            (qy - center_y) / frame.y_scale, (qx - center_x) / frame.x_scale
        )
        fx = frame.x_off + (0.5 + 0.5 * math.cos(theta)) * frame.x_scale
        fy = frame.y_off + (0.5 + 0.5 * math.sin(theta)) * frame.y_scale
        tx = -math.sin(theta) * frame.x_scale
        ty = math.cos(theta) * frame.y_scale
        length = math.hypot(tx, ty)
        ox, oy = ty / length, -tx / length
        if ox * (fx - center_x) + oy * (fy - center_y) < 0.0:
            ox, oy = -ox, -oy
        radius = math.hypot(fx + ox * half - center_x, fy + oy * half - center_y)
        worst = max(worst, math.hypot(qx - center_x, qy - center_y) - radius)
    assert worst <= 1.0


@pytest.mark.parametrize("glyph", ("A", "G"))
def test_batch_meets_the_on_curve_budget(glyph):
    resolved = _resolved(glyph)
    outline = _built(glyph)
    paths = fit_outline(outline, resolved.style)
    corner = float(resolved.style.curve["corner_deg"])
    limit = float(resolved.style.curve["max_error"])
    for contour, path in zip(outline.contours, paths, strict=True):
        points = [(point.x, point.y) for point in contour]
        assert len(path.on_curve_points()) <= max(12, _pins(contour, corner))
        assert hausdorff_path_to_polyline(path, points) <= limit + 1e-6


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return build_style("modern", glyphs=("A", "G"), out_dir=root)


@pytest.mark.parametrize("glyph", ("A", "G"))
def test_shipped_ttf_stays_on_the_design(compiled, glyph):
    resolved = _resolved(glyph)
    design = fit_outline(_built(glyph), resolved.style)
    worst, mean = outline_gap(design, compiled["ttf"], glyph)
    assert worst <= 1.0
    assert 0.0 <= mean <= 0.3
