"""モダンの K M N W。他の様式には足さない。"""

from __future__ import annotations

import math
import statistics
import tempfile
from itertools import pairwise
from pathlib import Path

import pytest

from engine.curve_fit import _polyline_extrema, detect_corners
from engine.latin.build import build_glyph
from engine.latin.compile import build_style, outline_gap
from engine.latin.gate import (
    metric_violations,
    overshoot_violations,
    side_gaps,
    vertical_stem_widths,
)
from engine.latin.load import load_resolved
from engine.latin.outline import _missing_extrema, fit_outline

_GLYPHS = ("K", "M", "N", "W")
_CAP = 700.0


def _built(glyph: str):
    return build_glyph(load_resolved(glyph, "modern"))


def _stem() -> float:
    return load_resolved("H", "modern").pen.stem * _CAP


def _ring(contour):
    pts = list(contour)
    if (
        len(pts) > 1
        and abs(pts[0].x - pts[-1].x) < 1e-6
        and abs(pts[0].y - pts[-1].y) < 1e-6
    ):
        return pts[:-1]
    return pts


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
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


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


def _portion(start, end, y0: float, y1: float):
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


def _long_edges(outline, y0: float, y1: float, turn_deg: float = 20.0):
    """帯の中の縁。曲がりが turn_deg を超えた所で分ける。"""
    ring = _ring(outline.contours[0])
    chains: list[list] = []
    current: list = []
    for start, end in pairwise(ring + ring[:1]):
        segment = _portion(start, end, y0, y1)
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
                if turn > turn_deg:
                    split.append(piece)
                    piece = [point]
        piece.append(chain[-1])
        split.append(piece)
    return [chain for chain in split if (chain[-1] - chain[0]).length() >= 80.0]


def _deviation(chain) -> float:
    start, end = chain[0], chain[-1]
    length = (end - start).length()
    if length < 1.0 or len(chain) < 3:
        return 0.0
    return max(
        abs((point - start).cross(end - start)) / length for point in chain[1:-1]
    )


def _seg_end(seg) -> tuple[float, float]:
    if seg[0] == "L":
        return (float(seg[1]), float(seg[2]))
    return (float(seg[5]), float(seg[6]))


def _line_line_turns(path) -> list[float]:
    if len(path.segs) < 2:
        return []
    ends = [_seg_end(seg) for seg in path.segs]
    found = []
    for index, kind in enumerate(path.segs):
        if path.segs[index - 1][0] != "L" or kind[0] != "L":
            continue
        before = ends[index - 2]
        point = ends[index - 1]
        after = ends[index]
        v1x, v1y = point[0] - before[0], point[1] - before[1]
        v2x, v2y = after[0] - point[0], after[1] - point[1]
        found.append(
            abs(math.degrees(math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y)))
        )
    return found


def _apex_factor(resolved, y: float) -> float:
    cap = resolved.style.cap_height
    tip = -resolved.style.overshoot["apex"] * cap
    taper = float(resolved.style.metrics["apex_taper"])
    return taper + (1.0 - taper) * (y - tip) / (cap - tip)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_batch_is_modern_only(glyph):
    """他の3様式の比例表には入れない。"""
    load_resolved(glyph, "modern")
    for style in ("classic", "chic", "pop"):
        with pytest.raises(ValueError):
            load_resolved(glyph, style)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_roles_stay_thick(glyph):
    """モダンは mono。thin も slant_thin も使わない。"""
    resolved = load_resolved(glyph, "modern")
    assert [stroke.role for stroke in resolved.skeleton.strokes] == ["thick"] * len(
        resolved.skeleton.strokes
    )


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_batch_matches_expected_contours(glyph):
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    assert outline.contour_count == resolved.skeleton.expect_contours
    assert outline.hole_count == resolved.skeleton.expect_holes
    assert outline.advance > 0
    assert metric_violations(outline, resolved.style) == []
    assert overshoot_violations(outline, resolved) == []


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_batch_keeps_extrema(glyph):
    """G-X。極値はオンカーブ点にある。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    assert paths
    assert all(_missing_extrema(path) == 0 for path in paths)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_batch_on_curve_count_stays_within_gf(glyph):
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


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_straight_edges_have_no_spare_nodes(glyph):
    """直線の上に、曲がり 1° 未満のオンカーブ点を置かない。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    for path in paths:
        assert all(turn >= 1.0 for turn in _line_line_turns(path))


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_outline_has_no_reverse_bend(glyph):
    """1° から 70° の、輪郭の向きと逆の折れがない。"""
    outer = _ring(_built(glyph).contours[0])
    sign = (
        1.0
        if sum(
            outer[i].x * outer[(i + 1) % len(outer)].y
            - outer[(i + 1) % len(outer)].x * outer[i].y
            for i in range(len(outer))
        )
        > 0.0
        else -1.0
    )
    overshoot = load_resolved(glyph, "modern").style.overshoot["apex"] * _CAP
    mild = []
    for index, turn in enumerate(_turns(outer)):
        if not (1.0 < abs(turn) < 70.0 and turn * sign < 0.0):
            continue
        point = outer[index]
        # 頂点の平切りは、この範囲の折れになる。裂け目ではない。
        on_cut = (
            abs(point.y - (_CAP + overshoot)) <= 1.5 or abs(point.y + overshoot) <= 1.5
        )
        if on_cut:
            continue
        mild.append(turn)
    assert mild == []


@pytest.mark.parametrize("glyph", ("K",))
def test_flat_letters_stay_on_the_bands(glyph):
    """平らな天地。尖りのオーバーシュートは付けない。"""
    ys = [point.y for contour in _built(glyph).contours for point in contour]
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert min(ys) == pytest.approx(0.0, abs=0.5)


@pytest.mark.parametrize("glyph", ("M", "W"))
def test_pointed_apex_overshoots_and_the_flat_side_does_not(glyph):
    """尖った頂点だけ overshoot.apex。天地の平らな縁は帯に乗る。"""
    resolved = load_resolved(glyph, "modern")
    ys = [point.y for contour in _built(glyph).contours for point in contour]
    apex = resolved.style.overshoot["apex"] * _CAP
    assert min(ys) == pytest.approx(-apex, abs=0.5)
    assert max(ys) == pytest.approx(_CAP + apex, abs=0.5)


@pytest.mark.parametrize("glyph", ("M", "W"))
def test_flat_tips_match_apex_flat(glyph):
    """平切りの幅は apex_flat × 幹。"""
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    want = float(resolved.style.metrics["apex_flat"]) * _stem()
    points = [point for contour in outline.contours for point in contour]
    ymin = min(point.y for point in points)
    low = sorted(
        (point for point in points if point.y < ymin + 0.8),
        key=lambda point: point.x,
    )
    groups: list[list] = []
    for point in low:
        if groups and point.x - groups[-1][-1].x < 80.0:
            groups[-1].append(point)
        else:
            groups.append([point])
    assert len(groups) == (2 if glyph == "W" else 1)
    for group in groups:
        width = max(point.x for point in group) - min(point.x for point in group)
        assert width == pytest.approx(want, abs=1.0)
        assert max(point.y for point in group) - ymin < 0.5


@pytest.mark.parametrize(
    ("glyph", "low", "high"),
    (("W", 0.45, 0.75),),
)
def test_apex_width_tapers_along_the_whole_leg(glyph, low, high):
    """0.25 と 0.75 のキャップ。脚が幹と分かれている高さで、太さは一次。"""
    resolved = load_resolved(glyph, "modern")
    outline = build_glyph(resolved)
    y0, y1 = low * _CAP, high * _CAP

    def widths(y: float) -> list[float]:
        runs = _runs(outline, y)
        assert len(runs) == 4
        # 外側の脚だけ。足から下の頂点へ、V と同じ先細り。
        return [runs[0][1] - runs[0][0], runs[-1][1] - runs[-1][0]]

    found = widths(y0)
    later = widths(y1)
    expect = _apex_factor(resolved, y0) / _apex_factor(resolved, y1)
    for early, late in zip(found, later, strict=True):
        assert early / late == pytest.approx(expect, rel=0.02)


def test_valley_stays_open_above_the_crotch():
    """谷は股の上で開いたまま。"""
    floor = 0.35 * _stem()
    for glyph in ("M", "W"):
        outline = _built(glyph)
        tip = min(point.y for contour in outline.contours for point in contour)
        opened = next(
            float(y)
            for y in range(int(tip) + 2, 680, 2)
            if len(_runs(outline, float(y))) == 4
        )
        runs = _runs(outline, opened + 70.0)
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        assert gaps
        assert min(gaps) >= floor


@pytest.mark.parametrize(
    ("glyph", "turn"),
    (("K", 20.0), ("M", 20.0), ("W", 20.0), ("N", 1.0)),
)
def test_straight_leg_edges_stay_straight(glyph, turn):
    """直線の脚の縁は、端点を結ぶ線から 0.5 UPM 以上ずれない。

    N は両端が股なので、細めが折り返す中央で縁を分ける。半分ずつが直線。
    """
    outline = _built(glyph)
    if glyph == "N":
        y0, y1 = 0.20 * _CAP, 0.80 * _CAP
    else:
        y0, y1 = 0.25 * _CAP, 0.75 * _CAP
    edges = _long_edges(outline, y0, y1, turn)
    assert len(edges) >= 4
    for edge in edges:
        assert _deviation(edge) <= 0.5


def test_k_arms_meet_on_the_stem():
    """腕と脚は幹の右縁で会う。内縁の点は一つ。"""
    resolved = load_resolved("K", "modern")
    path = fit_outline(build_glyph(resolved), resolved.style)[0]
    pts = path.on_curve_points()
    stem = sorted({round(point[0], 1) for point in pts})[1]
    between = [
        point
        for point in pts
        if abs(point[0] - stem) < 0.6 and 200.0 < point[1] < 500.0
    ]
    assert len(between) == 3
    ys = sorted(point[1] for point in between)
    assert ys[0] < ys[1] < ys[2]


def _band_edges(pts, band: float):
    edges = []
    for index in range(len(pts)):
        start, end = pts[index - 1], pts[index]
        if abs(start[0] - end[0]) < 1.0 or abs(start[1] - end[1]) < 1.0:
            continue
        if abs(start[1] - band) < 0.8 or abs(end[1] - band) < 0.8:
            edges.append((start, end))
    return edges


def _width_ratio_from_the_thin_end(edges) -> float:
    def ends(edge):
        start, end = edge
        if abs(start[1]) < 0.8 or abs(start[1] - _CAP) < 0.8:
            return end, start
        return start, end

    thin, full = ends(edges[0])
    other = edges[1]

    def width(t: float) -> float:
        x = thin[0] + (full[0] - thin[0]) * t
        y = thin[1] + (full[1] - thin[1]) * t
        ax, ay = other[0]
        bx, by = other[1]
        dx, dy = bx - ax, by - ay
        return abs((x - ax) * dy - (y - ay) * dx) / math.hypot(dx, dy)

    return width(0.25) / width(0.75)


def test_k_crotch_width_follows_crotch_thin():
    """腕と脚の墨は、股で crotch_thin、足で幹の太さ。途中は一次。"""
    resolved = load_resolved("K", "modern")
    path = fit_outline(build_glyph(resolved), resolved.style)[0]
    pts = path.on_curve_points()
    factor = resolved.style.joins["crotch_thin"]
    expect = (factor + (1.0 - factor) * 0.25) / (factor + (1.0 - factor) * 0.75)
    for band in (0.0, _CAP):
        edges = _band_edges(pts, band)
        assert len(edges) == 2
        assert _width_ratio_from_the_thin_end(edges) == pytest.approx(expect, rel=0.02)


def _on_curve(glyph: str):
    resolved = load_resolved(glyph, "modern")
    return fit_outline(build_glyph(resolved), resolved.style)[0].on_curve_points()


def _segments(pts):
    return [(pts[i - 1], pts[i]) for i in range(len(pts))]


def _long_diagonals(pts, min_dy: float):
    found = []
    for start, end in _segments(pts):
        if abs(end[0] - start[0]) < 1.0 or abs(end[1] - start[1]) < min_dy:
            continue
        found.append((start, end))
    return found


def _line_distance(point, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    return abs((point[0] - start[0]) * dy - (point[1] - start[1]) * dx) / length


def test_n_diagonal_is_straight_and_constantly_thin():
    """斜画の縁は端から端まで1本の直線。太さは全長で 0.90 × 幹。"""
    pts = _on_curve("N")
    edges = _long_diagonals(pts, 0.5 * _CAP)
    assert len(edges) == 2
    stem = _stem()
    widths = []
    for start, end in edges:
        other = edges[0] if (start, end) == edges[1] else edges[1]
        for t in (0.25, 0.5, 0.75):
            point = (
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
            )
            widths.append(_line_distance(point, other[0], other[1]))
    assert max(widths) == pytest.approx(min(widths), rel=0.01)
    assert widths[0] == pytest.approx(0.90 * stem, rel=0.01)


def _flats_near(pts, y: float, tol: float = 1.5) -> list[float]:
    found = []
    for start, end in _segments(pts):
        if abs(start[1] - y) > tol or abs(end[1] - y) > tol:
            continue
        if abs(start[1] - end[1]) > 0.5:
            continue
        found.append(abs(end[0] - start[0]))
    return found


@pytest.mark.parametrize(
    ("glyph", "n_top", "n_bottom"),
    (("M", 2, 1), ("N", 1, 1), ("W", 1, 2)),
)
def test_apex_flats_match_the_cut_and_overshoot(glyph, n_top, n_bottom):
    """頂点の平切りは 0.45 × 幹。上はキャップ＋尖り、下は −尖り。"""
    resolved = load_resolved(glyph, "modern")
    pts = _on_curve(glyph)
    overshoot = resolved.style.overshoot["apex"] * _CAP
    want = 0.45 * _stem()
    top = _flats_near(pts, _CAP + overshoot)
    bottom = _flats_near(pts, -overshoot)
    assert len(top) == n_top
    assert len(bottom) == n_bottom
    for width in top + bottom:
        assert width == pytest.approx(want, abs=2.0)
    ys = [point[1] for point in pts]
    assert max(ys) == pytest.approx(_CAP + overshoot, abs=1.0)
    assert min(ys) == pytest.approx(-overshoot, abs=1.0)
    for start, end in _segments(pts):
        on_flat = abs(start[1] - end[1]) < 0.5 and (
            abs(start[1] - (_CAP + overshoot)) <= 1.5
            or abs(start[1] + overshoot) <= 1.5
        )
        if not on_flat:
            continue
        # 平切りの両隣は、頂点へ入る外縁。途中に点を挟まない。
        assert math.hypot(end[0] - start[0], end[1] - start[1]) == pytest.approx(
            want, abs=2.0
        )


def test_apex_outer_edges_have_no_spare_points():
    """頂点の平切りから出る外縁は、次の角まで1本の直線。"""
    for glyph in ("M", "N", "W"):
        resolved = load_resolved(glyph, "modern")
        pts = _on_curve(glyph)
        overshoot = resolved.style.overshoot["apex"] * _CAP
        flats = set()
        for index, (start, end) in enumerate(_segments(pts)):
            if abs(start[1] - end[1]) > 0.5:
                continue
            if (
                abs(start[1] - (_CAP + overshoot)) <= 1.5
                or abs(start[1] + overshoot) <= 1.5
            ):
                flats.add(index)
        assert flats
        for index in flats:
            for neighbor in (index - 1, index + 1):
                start, end = _segments(pts)[neighbor % len(pts)]
                assert math.hypot(end[0] - start[0], end[1] - start[1]) > 100.0


def test_m_and_n_apex_corners_are_not_square_stem_caps():
    """M の天と N の頂点側に、幹幅の水平な天を置かない。"""
    stem = _stem()
    m_pts = _on_curve("M")
    square = [
        abs(end[0] - start[0])
        for start, end in _segments(m_pts)
        if abs(start[1] - _CAP) < 1.0
        and abs(end[1] - _CAP) < 1.0
        and abs(end[0] - start[0]) > 0.7 * stem
    ]
    assert square == []
    n_pts = _on_curve("N")
    left = min(point[0] for point in n_pts)
    n_square = [
        abs(end[0] - start[0])
        for start, end in _segments(n_pts)
        if abs(start[1] - _CAP) < 1.0
        and abs(end[1] - _CAP) < 1.0
        and min(start[0], end[0]) < left + stem
        and abs(end[0] - start[0]) > 0.7 * stem
    ]
    assert n_square == []


def test_n_crotch_width_follows_crotch_thin():
    """両端が頂点の斜画は、全長が crotch_thin 倍。"""
    test_n_diagonal_is_straight_and_constantly_thin()


def _down_diagonals(pts):
    found = []
    for start, end in _segments(pts):
        dx, dy = end[0] - start[0], end[1] - start[1]
        if abs(dy) < 100.0 or abs(dx) < 20.0:
            continue
        if dy > 0.0:
            start, end = end, start
        angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
        found.append((start, end, angle))
    return found


def _diagonal_sides(pts):
    cx = (min(point[0] for point in pts) + max(point[0] for point in pts)) / 2.0
    sides = {"left": [], "right": []}
    for start, end, angle in _down_diagonals(pts):
        mid_x = (start[0] + end[0]) / 2.0
        sides["left" if mid_x < cx else "right"].append((start, end, angle))
    return sides


def test_m_is_mirror_symmetric():
    """M は墨の箱の中央で左右対称。各オンカーブ点の鏡像が 1 UPM 以内にある。"""
    pts = _on_curve("M")
    center = (min(point[0] for point in pts) + max(point[0] for point in pts)) / 2.0
    for x, y in pts:
        image = (2.0 * center - x, y)
        nearest = min(math.hypot(image[0] - qx, image[1] - qy) for qx, qy in pts)
        assert nearest <= 1.0


def test_m_diagonals_are_parallel_and_constantly_wide():
    """斜画の両端は頂点。縁は 0.3° 以内で平行、直角の太さは全長で 0.90 × 幹。"""
    pts = _on_curve("M")
    stem = _stem()
    for edges in _diagonal_sides(pts).values():
        assert len(edges) == 2
        (start, end, angle), (other_start, other_end, other_angle) = edges
        assert abs(angle - other_angle) < 0.3
        widths = []
        for t in (0.25, 0.5, 0.75):
            point = (
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
            )
            widths.append(_line_distance(point, other_start, other_end))
        assert max(widths) == pytest.approx(min(widths), rel=0.01)
        assert widths[0] == pytest.approx(0.90 * stem, rel=0.01)


def test_m_outer_edges_into_each_apex_are_single_lines():
    """頂点の平切りから出る外縁は、次の角まで他の点が乗らない1本の直線。"""
    resolved = load_resolved("M", "modern")
    pts = _on_curve("M")
    overshoot = resolved.style.overshoot["apex"] * _CAP
    segments = _segments(pts)
    flats = [
        index
        for index, (start, end) in enumerate(segments)
        if abs(start[1] - end[1]) <= 0.5
        and (
            abs(start[1] - (_CAP + overshoot)) <= 1.5
            or abs(start[1] + overshoot) <= 1.5
        )
    ]
    assert len(flats) == 3
    for index in flats:
        for neighbor in (index - 1, index + 1):
            start, end = segments[neighbor % len(pts)]
            if abs(start[0] - end[0]) < 1.0:
                continue
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            assert length > 100.0
            for x, y in pts:
                if math.hypot(x - start[0], y - start[1]) <= 1.0:
                    continue
                if math.hypot(x - end[0], y - end[1]) <= 1.0:
                    continue
                t = ((x - start[0]) * dx + (y - start[1]) * dy) / (length * length)
                if not 0.02 < t < 0.98:
                    continue
                assert abs((x - start[0]) * dy - (y - start[1]) * dx) / length > 1.0


def test_n_is_point_symmetric_about_its_ink():
    """N は墨の箱の中心で点対称。回した各オンカーブ点が 1 UPM 以内にある。"""
    pts = _on_curve("N")
    cx = (min(point[0] for point in pts) + max(point[0] for point in pts)) / 2.0
    cy = (min(point[1] for point in pts) + max(point[1] for point in pts)) / 2.0
    for x, y in pts:
        image = (2.0 * cx - x, 2.0 * cy - y)
        nearest = min(math.hypot(image[0] - qx, image[1] - qy) for qx, qy in pts)
        assert nearest <= 1.0


def test_n_bottom_right_apex_flat():
    """右下の平切りは 41、高さは −尖り。段は付けない。"""
    pts = _on_curve("N")
    right = max(point[0] for point in pts)
    found = []
    for start, end in _segments(pts):
        if abs(start[1] - end[1]) > 0.5:
            continue
        if max(start[0], end[0]) < right - 1.0:
            continue
        y = (start[1] + end[1]) / 2.0
        if y > 100.0:
            continue
        found.append((abs(end[0] - start[0]), y))
    assert len(found) == 1
    width, y = found[0]
    assert width == pytest.approx(41.0, abs=2.0)
    assert y == pytest.approx(-8.4, abs=1.0)


def test_w_middle_is_above_the_cap():
    """中央の山はキャップより上の平切り。幹幅の天は残さない。"""
    resolved = load_resolved("W", "modern")
    pts = fit_outline(build_glyph(resolved), resolved.style)[0].on_curve_points()
    overshoot = resolved.style.overshoot["apex"] * _CAP
    center = (min(point[0] for point in pts) + max(point[0] for point in pts)) / 2.0
    on_cap = []
    for index in range(len(pts)):
        start, end = pts[index - 1], pts[index]
        if abs(start[1] - _CAP) > 0.5 or abs(end[1] - _CAP) > 0.5:
            continue
        mid = (start[0] + end[0]) / 2.0
        if abs(mid - center) < 80.0:
            on_cap.append(abs(end[0] - start[0]))
    assert on_cap == []
    peaks = _flats_near(pts, _CAP + overshoot)
    assert len(peaks) == 1
    assert peaks[0] == pytest.approx(0.45 * _stem(), abs=2.0)


@pytest.mark.parametrize("glyph", ("K", "M", "N"))
def test_vertical_stems_match_h(glyph):
    outlines = {"H": _built("H"), glyph: _built(glyph)}
    middle = statistics.median(vertical_stem_widths(outlines["H"]))
    found = statistics.median(vertical_stem_widths(outlines[glyph]))
    assert abs(found - middle) / middle <= 0.05


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_side_gaps_match_the_class(glyph):
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
    assert left == pytest.approx(expect_left, abs=0.5)
    assert right == pytest.approx(expect_right, abs=0.5)


def _design(glyph: str):
    resolved = load_resolved(glyph, "modern")
    return fit_outline(build_glyph(resolved), resolved.style)


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return build_style("modern", glyphs=_GLYPHS, out_dir=root)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_shipped_ttf_stays_on_the_design(compiled, glyph):
    """G-TT。TTF の最大 ≤ 1.0、平均は 0 以上 0.3 以下。"""
    worst, mean = outline_gap(_design(glyph), compiled["ttf"], glyph)
    assert worst <= 1.0
    assert 0.0 <= mean <= 0.3
