"""モダンの曲線4字（C D J U）。股はなく、丸い部分だけオーバーシュートする。"""

from __future__ import annotations

import math
import statistics
import tempfile
from itertools import pairwise
from pathlib import Path

import pytest

from engine.curve_fit import _polyline_extrema, detect_corners
from engine.latin.build import _centerline, _fit_bowls, _stroke_resolved, build_glyph
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

_GLYPHS = ("C", "D", "J", "U")
_CAP = 700.0


def _built(glyph: str):
    return build_glyph(load_resolved(glyph, "modern"))


def _round(resolved) -> float:
    return resolved.style.overshoot["round"] * resolved.style.cap_height


def _outer(outline):
    return next(
        contour for contour, hole in zip(outline.contours, outline.holes) if not hole
    )


def _area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    count = len(points)
    for index in range(count):
        nxt = points[(index + 1) % count]
        total += points[index][0] * nxt[1] - nxt[0] * points[index][1]
    return 0.5 * total


def _turns(pts) -> list[float]:
    found = []
    count = len(pts)
    for index, point in enumerate(pts):
        prev = pts[index - 1]
        nxt = pts[(index + 1) % count]
        v1x, v1y = point.x - prev.x, point.y - prev.y
        v2x, v2y = nxt.x - point.x, nxt.y - point.y
        found.append(
            math.degrees(math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y))
        )
    return found


def _runs_at_y(outline, y: float) -> list[tuple[float, float]]:
    xs: list[float] = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            if (start.y - y) * (end.y - y) > 0.0 or abs(end.y - start.y) < 1e-9:
                continue
            t = (y - start.y) / (end.y - start.y)
            if 0.0 <= t < 1.0:
                xs.append(start.x + (end.x - start.x) * t)
    xs.sort()
    if len(xs) < 2 or len(xs) % 2:
        return []
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs), 2)]


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_curve_glyph_matches_expected_contours(glyph):
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    assert outline.contour_count == resolved.skeleton.expect_contours
    assert outline.hole_count == resolved.skeleton.expect_holes
    assert outline.advance > 0


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_curve_fit_keeps_extrema_and_straight_segments(glyph):
    """G-X・G-F・G-L。直線の区間だけ軸に平行。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert paths
    assert all(_missing_extrema(path) == 0 for path in paths)
    for path in paths:
        cur = path.start
        for seg in path.segs:
            if seg[0] != "L":
                cur = (seg[5], seg[6])
                continue
            end = (seg[1], seg[2])
            assert end[0] == cur[0] or end[1] == cur[1]
            cur = end


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_curve_contours_start_at_the_lowest_point_and_wind(glyph):
    """G-ORD。"""
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


def test_c_overshoots_on_both_crowns():
    """C の天地は丸のオーバーシュート。"""
    resolved = load_resolved("C", "modern")
    outline = _built("C")
    ys = [point.y for contour in outline.contours for point in contour]
    over = _round(resolved)
    assert min(ys) == pytest.approx(-over, abs=1.0)
    assert max(ys) == pytest.approx(_CAP + over, abs=1.0)
    assert overshoot_violations(outline, resolved) == []
    assert metric_violations(outline, resolved.style) == []


def test_d_joined_bowl_is_flat():
    """幹に付いた碗は B と同じく、外形の天地が 0 とキャップ。"""
    resolved = load_resolved("D", "modern")
    outline = _built("D")
    outer = list(_outer(outline))
    assert max(point.y for point in outer) == pytest.approx(_CAP, abs=0.5)
    assert min(point.y for point in outer) == pytest.approx(0.0, abs=0.5)
    assert metric_violations(outline, resolved.style) == []


def test_j_top_is_flat_and_the_bottom_only_overshoots():
    """J の天は平ら。底は丸のオーバーシュートまでで、ディセンダーへは下ろさない。"""
    resolved = load_resolved("J", "modern")
    outline = _built("J")
    ys = [point.y for contour in outline.contours for point in contour]
    over = _round(resolved)
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert min(ys) == pytest.approx(-over, abs=1.0)
    assert min(ys) > resolved.style.vertical["descender"] + 100.0
    assert metric_violations(outline, resolved.style) == []


def test_u_stems_are_flat_and_the_bottom_overshoots():
    """U の幹の天はキャップ。底の弧だけ丸のオーバーシュート。"""
    resolved = load_resolved("U", "modern")
    outline = _built("U")
    ys = [point.y for contour in outline.contours for point in contour]
    over = _round(resolved)
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert min(ys) == pytest.approx(-over, abs=1.0)
    assert metric_violations(outline, resolved.style) == []


def test_vertical_stems_stay_within_five_percent_of_h():
    """G-SET。縦ステムの中央値は H から 5% 以内。"""
    outlines = {"H": _built("H")}
    outlines.update({glyph: _built(glyph) for glyph in _GLYPHS})
    middle = statistics.median(vertical_stem_widths(outlines["H"]))
    assert middle > 0.0
    for glyph in _GLYPHS:
        widths = vertical_stem_widths(outlines[glyph])
        if not widths:
            continue
        found = statistics.median(widths)
        assert abs(found - middle) / middle <= 0.05
    assert stem_set_violations(outlines) == []


@pytest.mark.parametrize("glyph", ("D", "J", "U"))
def test_curve_meets_the_stem_without_a_kink(glyph):
    """幹と曲線のつなぎに、直角でもない折れや逆向きの段がない。"""
    pts = list(_outer(_built(glyph)))
    if (
        len(pts) > 1
        and abs(pts[0].x - pts[-1].x) < 1e-6
        and abs(pts[0].y - pts[-1].y) < 1e-6
    ):
        pts = pts[:-1]
    for turn in _turns(pts):
        assert abs(turn) <= 12.0 or abs(turn) >= 80.0


def test_monoline_walls_stay_near_the_stem():
    """曲線の壁も、幹の太さから大きく外れない。"""
    stem = load_resolved("H", "modern").pen.stem * _CAP
    checks = (
        ("C", 350.0, "left"),
        ("D", 350.0, "right"),
        ("J", 500.0, "right"),
        ("U", 500.0, "left"),
    )
    for glyph, y, side in checks:
        runs = _runs_at_y(_built(glyph), y)
        assert runs
        chosen = runs[0] if side == "left" else runs[-1]
        width = chosen[1] - chosen[0]
        assert width == pytest.approx(stem, abs=8.0)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_side_gaps_are_not_negative(glyph):
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


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return build_style("modern", glyphs=_GLYPHS, out_dir=root)


def _design(glyph: str):
    resolved = load_resolved(glyph, "modern")
    return fit_outline(build_glyph(resolved), resolved.style)


def _ring(contour):
    pts = list(contour)
    if (
        len(pts) > 1
        and abs(pts[0].x - pts[-1].x) < 1e-6
        and abs(pts[0].y - pts[-1].y) < 1e-6
    ):
        return pts[:-1]
    return pts


def _tangent_turns(samples) -> list[float]:
    found = []
    for prev, cur in pairwise(samples):
        before, after = prev[1], cur[1]
        found.append(
            math.degrees(
                math.atan2(
                    before.x * after.y - before.y * after.x,
                    before.x * after.x + before.y * after.y,
                )
            )
        )
    return found


def _bowl_centerline(glyph: str):
    resolved = load_resolved(glyph, "modern")
    frames, _width = _fit_bowls(resolved)
    stroke = next(item for item in resolved.skeleton.strokes if item.id == "bowl")
    samples, _widths = _centerline(
        stroke, _stroke_resolved(stroke, resolved), frames.get(stroke.id)
    )
    return samples


def _arc_runs(pts, corner_deg: float = 45.0):
    """切り口の角で輪郭を切り、弧の区間だけを返す。"""
    turns = _turns(pts)
    corners = [index for index, turn in enumerate(turns) if abs(turn) >= corner_deg]
    if len(corners) < 2:
        return [pts]
    runs = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        if end > start:
            runs.append(pts[start : end + 1])
        else:
            runs.append(pts[start:] + pts[: end + 1])
    return runs


def _open_turns(pts) -> list[float]:
    found = []
    for index in range(1, len(pts) - 1):
        prev, point, nxt = pts[index - 1], pts[index], pts[index + 1]
        v1x, v1y = point.x - prev.x, point.y - prev.y
        v2x, v2y = nxt.x - point.x, nxt.y - point.y
        found.append(
            math.degrees(math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y))
        )
    return found


def _reversals(run, limit: float = 1.0) -> list[float]:
    kept = [turn for turn in _open_turns(run) if abs(turn) >= 0.25]
    if not kept:
        return []
    sign = 1.0 if sum(kept) >= 0.0 else -1.0
    return [turn for turn in kept if turn * sign < -limit]


def _segment_distance(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _mirror_gap(pts) -> float:
    xs = [point.x for point in pts]
    cx = (min(xs) + max(xs)) / 2.0
    mirrored = [(2.0 * cx - point.x, point.y) for point in pts]
    source = [(point.x, point.y) for point in pts]
    count = len(mirrored)

    def directed(points, edges) -> float:
        worst = 0.0
        for px, py in points:
            best = min(
                _segment_distance(
                    px,
                    py,
                    edges[i][0],
                    edges[i][1],
                    edges[(i + 1) % count][0],
                    edges[(i + 1) % count][1],
                )
                for i in range(count)
            )
            worst = max(worst, best)
        return worst

    return max(directed(source, mirrored), directed(mirrored, source))


def test_c_centerline_keeps_one_curvature_sign():
    """C の中心線は端から端まで、曲がりの向きが一定。"""
    turns = [turn for turn in _tangent_turns(_bowl_centerline("C")) if abs(turn) >= 0.2]
    assert turns
    sign = 1.0 if sum(turns) > 0.0 else -1.0
    assert all(turn * sign > 0.0 for turn in turns)


@pytest.mark.parametrize("glyph", ("C", "J", "U"))
def test_arc_runs_do_not_reverse(glyph):
    """弧の区間だけ見る。切り口の角と、内周と外周の境は含めない。"""
    outline = _built(glyph)
    for contour in outline.contours:
        for run in _arc_runs(_ring(contour)):
            assert _reversals(run) == []


def test_d_outer_has_no_reverse_bend():
    """D の外形に、1° を超える逆向きの折れがない。"""
    pts = _ring(_outer(_built("D")))
    sign = 1.0 if _area([(point.x, point.y) for point in pts]) > 0.0 else -1.0
    assert all(turn * sign > -1.0 for turn in _turns(pts))


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_curve_on_curve_count_stays_within_gf(glyph):
    """G-F。オンカーブ点は 12 か、角と極値の数の、大きい方まで。"""
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    corner_deg = float(resolved.style.curve["corner_deg"])
    paths = fit_outline(outline, resolved.style)
    for contour, path in zip(outline.contours, paths, strict=True):
        points = [(point.x, point.y) for point in _ring(contour)]
        pins = set(detect_corners(points, angle_deg=corner_deg, min_sep_upm=10.0))
        pins.update(_polyline_extrema(points))
        assert len(path.on_curve_points()) <= max(12, len(pins))


def test_u_contour_is_mirror_symmetric():
    """U の輪郭を左右に折り返すと、0.5 UPM 以内で重なる。"""
    assert _mirror_gap(_ring(_built("U").contours[0])) <= 0.5


@pytest.mark.parametrize("kind", ("otf", "ttf"))
@pytest.mark.parametrize("glyph", _GLYPHS)
def test_shipped_curve_outline_stays_on_the_design(compiled, glyph, kind):
    """G-TT。最大 ≤ 1.0、平均は 0 以上 0.3 以下。"""
    worst, mean = outline_gap(_design(glyph), compiled[kind], glyph)
    assert worst <= 1.0
    assert 0.0 <= mean <= 0.3
