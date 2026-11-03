"""天の apex は V を上下に反転した作り。横棒の高さは骨格の y に残す。"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

import pytest

from engine.curve_fit import _polyline_extrema, detect_corners
from engine.latin.build import build_glyph
from engine.latin.gate import _apex_bands, overshoot_violations
from engine.latin.load import load_style, resolve, styles_dir
from engine.latin.outline import fit_outline
from engine.latin.schema import parse_skeleton

_CAP = 700.0
_BAR_Y = 0.32


def _style():
    style = load_style(styles_dir() / "modern.yaml")
    return replace(style, proportions={**style.proportions, "A": 0.78})


def _resolved(bar_y: float | None = None):
    strokes = [
        {
            "id": "left",
            "knots": [[0.08, 0.00, "line"], [0.50, 1.00, "line"]],
            "role": "thick",
            "ends": {"start": "foot", "end": "apex"},
        },
        {
            "id": "right",
            "knots": [[0.50, 1.00, "line"], [0.92, 0.00, "line"]],
            "role": "thick",
            "ends": {"start": "apex", "end": "foot"},
        },
    ]
    if bar_y is not None:
        # 脚の中心より少し外側まで伸ばし、墨の中で会わせる。
        left_x = 0.08 + bar_y * (0.50 - 0.08) - 0.04
        right_x = 0.92 - bar_y * (0.92 - 0.50) + 0.04
        strokes.append(
            {
                "id": "cross",
                "knots": [[left_x, bar_y, "line"], [right_x, bar_y, "line"]],
                "role": "arm",
                "ends": {"start": "none", "end": "none"},
            }
        )
    raw = {
        "glyph": "A",
        "unicode": 0x41,
        "structure": "apex_diagonals",
        "groups": ["diagonal"],
        "strokes": strokes,
        "joins": [{"a": "left", "b": "right", "type": "apex"}],
        "sides": {"left": "diagonal", "right": "diagonal"},
        "expect": {"contours": 1, "holes": 0},
    }
    return resolve(parse_skeleton(raw), _style())


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


def _points(outline):
    return [point for contour in outline.contours for point in contour]


def _valley(outline) -> float:
    """先端の下で、脚が二つに分かれる高さ。"""
    tip = max(point.y for point in _points(outline))
    for y in range(int(tip) - 2, 40, -2):
        if len(_runs(outline, float(y))) == 2:
            return float(y)
    raise AssertionError("valley never opens")


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
    return chains


def _ring(contour):
    pts = list(contour)
    if len(pts) > 1 and (pts[0] - pts[-1]).length() < 1e-6:
        return pts[:-1]
    return pts


def _turns(pts):
    found = []
    for index, point in enumerate(pts):
        prev, nxt = pts[index - 1], pts[(index + 1) % len(pts)]
        d1, d2 = point - prev, nxt - point
        if d1.length() < 0.4 or d2.length() < 0.4:
            continue
        found.append(math.degrees(math.atan2(d1.cross(d2), d1.dot(d2))))
    return found


def test_top_apex_is_a_flat_cut_above_the_cap():
    resolved = _resolved()
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    peak = cap + resolved.style.overshoot["apex"] * cap
    want = resolved.style.metrics["apex_flat"] * resolved.style.pen.stem * cap
    points = _points(outline)
    ymax = max(point.y for point in points)
    assert ymax == pytest.approx(peak, abs=1.0)
    flat = [point for point in points if point.y > ymax - 0.8]
    assert max(point.x for point in flat) - min(
        point.x for point in flat
    ) == pytest.approx(want, abs=2.0)
    assert max(point.y for point in flat) - min(point.y for point in flat) < 0.5


def test_top_apex_feet_are_flat_on_the_baseline():
    outline = build_glyph(_resolved())
    points = _points(outline)
    ymin = min(point.y for point in points)
    assert ymin == pytest.approx(0.0, abs=1.0)
    feet = [point for point in points if point.y < ymin + 0.8]
    assert max(point.y for point in feet) - ymin < 0.5
    feet.sort(key=lambda point: point.x)
    splits = [
        index
        for index in range(1, len(feet))
        if feet[index].x - feet[index - 1].x > 100.0
    ]
    assert len(splits) == 1
    for cluster in (feet[: splits[0]], feet[splits[0] :]):
        assert (
            max(point.x for point in cluster) - min(point.x for point in cluster) > 20.0
        )


def test_top_apex_leg_edges_are_straight():
    outline = build_glyph(_resolved())
    valley = _valley(outline)
    long = []
    for contour in outline.contours:
        for chain in _chains(contour, 20.0, valley - 12.0):
            if (chain[-1] - chain[0]).length() < 80.0:
                continue
            long.append(chain)
            assert _deviation(chain) <= 0.5
    assert len(long) == 4


def test_top_apex_taper_follows_the_leg_formula():
    """足で 1、先端で apex_taper。0.25 と 0.75 キャップは一次の比。"""
    resolved = _resolved()
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    peak = cap + resolved.style.overshoot["apex"] * cap
    taper = resolved.style.metrics["apex_taper"]
    samples = (0.25 * cap, 0.75 * cap)

    def factor(y: float) -> float:
        return taper + (1.0 - taper) * (peak - y) / peak

    widths = []
    for y in samples:
        runs = _runs(outline, y)
        assert len(runs) == 2
        widths.append([run[1] - run[0] for run in runs])
    for index in (0, 1):
        ratio = widths[0][index] / widths[1][index]
        expect = factor(samples[0]) / factor(samples[1])
        assert ratio == pytest.approx(expect, rel=0.02)


def test_top_apex_valley_stays_open():
    resolved = _resolved()
    outline = build_glyph(resolved)
    stem = resolved.style.pen.stem * resolved.style.cap_height
    valley = _valley(outline)
    runs = _runs(outline, valley - 70.0)
    assert len(runs) == 2
    gap = runs[1][0] - runs[0][1]
    assert gap >= 0.35 * stem


def test_top_apex_overshoot_is_the_top_band_only():
    resolved = _resolved()
    outline = build_glyph(resolved)
    assert _apex_bands(resolved.skeleton) == {"top"}
    assert overshoot_violations(outline, resolved) == []


def test_top_apex_fits_within_the_node_budget():
    resolved = _resolved()
    outline = build_glyph(resolved)
    paths = fit_outline(outline, resolved.style)
    corner = float(resolved.style.curve["corner_deg"])
    for contour, path in zip(outline.contours, paths, strict=True):
        points = [(point.x, point.y) for point in _ring(contour)]
        pins = set(detect_corners(points, angle_deg=corner, min_sep_upm=10.0))
        pins.update(_polyline_extrema(points))
        assert len(path.on_curve_points()) <= max(12, len(pins))


def test_crossbar_keeps_its_height_and_joins_without_notches():
    """横棒は arm。中心は骨格の y のまま。bar にすると bar_y へ寄る。"""
    resolved = _resolved(_BAR_Y)
    plain = build_glyph(_resolved())
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    stem = resolved.style.pen.stem * cap
    want = resolved.pen.bar_ratio * stem
    center = _BAR_Y * cap
    points = _points(outline)
    assert min(point.x for point in points) == pytest.approx(
        min(point.x for point in _points(plain)), abs=1.0
    )
    assert max(point.x for point in points) == pytest.approx(
        max(point.x for point in _points(plain)), abs=1.0
    )
    horizontals = []
    for contour in outline.contours:
        ring = _ring(contour)
        for start, end in pairwise(ring + ring[:1]):
            if abs(end.y - start.y) > 0.6 or abs(end.x - start.x) < 40.0:
                continue
            if abs((start.y + end.y) / 2.0 - center) > want:
                continue
            horizontals.append((start.y + end.y) / 2.0)
    assert horizontals
    top = max(horizontals)
    bottom = min(horizontals)
    assert top - bottom == pytest.approx(want, abs=2.0)
    assert (top + bottom) / 2.0 == pytest.approx(center, abs=2.0)
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
        for index, turn in enumerate(_turns(ring)):
            if not (1.0 < abs(turn) < 70.0 and turn * sign < 0.0):
                continue
            point = ring[index]
            if abs(point.y - peak) <= 1.5 or abs(point.y) <= 1.5:
                continue
            mild.append((round(point.x, 1), round(point.y, 1), round(turn, 1)))
        assert mild == []
    paths = fit_outline(outline, resolved.style)
    corner = float(resolved.style.curve["corner_deg"])
    for contour, path in zip(outline.contours, paths, strict=True):
        pts = [(point.x, point.y) for point in _ring(contour)]
        pins = set(detect_corners(pts, angle_deg=corner, min_sep_upm=10.0))
        pins.update(_polyline_extrema(pts))
        assert len(path.on_curve_points()) <= max(12, len(pins))
