"""モダンの P R Z X Y とスラッシュ。他の様式には足さない。"""

from __future__ import annotations

import math
import statistics
import tempfile
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

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

_GLYPHS = ("P", "R", "Z", "X", "Y", "slash")
_CAP = 700.0


def _built(glyph: str):
    return build_glyph(load_resolved(glyph, "modern"))


def _round_stem() -> float:
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


def _outer(outline):
    return next(
        contour for contour, hole in zip(outline.contours, outline.holes) if not hole
    )


def _ys(outline) -> list[float]:
    return [point.y for contour in outline.contours for point in contour]


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


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_batch_is_modern_only(glyph):
    """他の3様式の比例表には入れない。"""
    load_resolved(glyph, "modern")
    for style in ("classic", "chic", "pop"):
        with pytest.raises(ValueError):
            load_resolved(glyph, style)


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


@pytest.mark.parametrize("glyph", ("P", "R", "Z", "X", "Y", "slash"))
def test_flat_letters_stay_on_the_bands(glyph):
    """平らな天地。尖りのオーバーシュートは付けない。"""
    ys = _ys(_built(glyph))
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert min(ys) == pytest.approx(0.0, abs=0.5)


def test_p_bowl_stays_above_the_bar():
    """P の碗は上半分。カウンターがあり、幹だけが基線まで降りる。"""
    outline = _built("P")
    stem = _round_stem()
    shoulder = _runs_at_y(outline, 680.0)
    lower = _runs_at_y(outline, 80.0)
    counter = _runs_at_y(outline, 500.0)
    assert len(shoulder) == 1
    assert shoulder[0][1] - shoulder[0][0] > stem * 2.5
    assert len(lower) == 1
    assert lower[0][1] - lower[0][0] == pytest.approx(stem, abs=4.0)
    assert len(counter) == 2


def test_r_leg_is_flat_on_the_baseline():
    """R の脚は基線で平切り。オーバーシュートも拍車も無い。"""
    outline = _built("R")
    outer = _ring(_outer(outline))
    assert min(point.y for point in outer) == pytest.approx(0.0, abs=0.5)
    assert max(point.y for point in outer) == pytest.approx(_CAP, abs=0.5)
    floor = [point.x for point in outer if point.y <= 0.5]
    assert max(floor) - min(floor) > 200.0
    assert len(_runs_at_y(outline, 40.0)) >= 2


def test_r_leg_does_not_notch_the_bowl():
    """脚が碗に入る所に、細い裂け目や逆向きの小さな折れがない。"""
    outer = _ring(_outer(_built("R")))
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
    mild = [
        turn for turn in _turns(outer) if 1.0 < abs(turn) < 70.0 and turn * sign < 0.0
    ]
    assert mild == []


def test_z_arms_do_not_spike_past_the_bands():
    """Z の腕の外へ、斜画の角がはみ出さない。"""
    outline = _built("Z")
    ys = _ys(outline)
    assert max(ys) == pytest.approx(_CAP, abs=0.5)
    assert min(ys) == pytest.approx(0.0, abs=0.5)
    top = _runs_at_y(outline, _CAP - 2.0)
    bottom = _runs_at_y(outline, 2.0)
    assert len(top) == 1 and len(bottom) == 1
    assert top[0][1] - top[0][0] > 80.0
    assert bottom[0][1] - bottom[0][0] > 80.0


def test_x_diagonals_match_the_stem_and_stay_flat():
    """X の斜画は幹と同じ太さ。端は天地で平切り。"""
    outline = _built("X")
    stem = _round_stem()
    runs = _runs_at_y(outline, 580.0)
    assert len(runs) == 2
    angle = math.atan2(_CAP, load_resolved("X", "modern").style.proportions["X"] * _CAP)
    expect = stem / math.sin(angle)
    for left, right in runs:
        assert right - left == pytest.approx(expect, abs=4.0)


def test_y_junction_does_not_pinch():
    """Y の腕は局所で細めない。幹は基線まで垂直。"""
    outline = _built("Y")
    stem = _round_stem()
    low = _runs_at_y(outline, 80.0)
    assert len(low) == 1
    assert low[0][1] - low[0][0] == pytest.approx(stem, abs=4.0)
    upper = _runs_at_y(outline, 620.0)
    assert len(upper) == 2
    angle = math.atan2(_CAP, load_resolved("Y", "modern").style.proportions["Y"] * _CAP)
    expect = stem / math.sin(angle)
    for left, right in upper:
        assert right - left == pytest.approx(expect, abs=8.0)


def test_slash_is_sixty_degrees_and_full_height():
    """スラッシュは基線からキャップまで。角度は暫定の 60°。"""
    resolved = load_resolved("slash", "modern")
    assert resolved.skeleton.glyph == "/"
    assert resolved.skeleton.unicode == 0x002F
    outline = build_glyph(resolved)
    outer = _ring(_outer(outline))
    top = [point for point in outer if point.y > _CAP - 1.0]
    bottom = [point for point in outer if point.y < 1.0]
    assert top and bottom
    top_x = sum(point.x for point in top) / len(top)
    bot_x = sum(point.x for point in bottom) / len(bottom)
    angle = math.degrees(math.atan2(_CAP, top_x - bot_x))
    assert angle == pytest.approx(60.0, abs=0.5)
    stem = _round_stem()
    runs = _runs_at_y(outline, _CAP / 2.0)
    assert len(runs) == 1
    width = runs[0][1] - runs[0][0]
    assert width == pytest.approx(stem / math.sin(math.radians(60.0)), abs=4.0)


@pytest.mark.parametrize("glyph", ("P", "R", "Y"))
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


def _seg_end(seg) -> tuple[float, float]:
    if seg[0] == "L":
        return (float(seg[1]), float(seg[2]))
    return (float(seg[5]), float(seg[6]))


def _line_line_turns(path) -> list[float]:
    """オンカーブ点が、直線と直線のあいだで何度曲がるか。"""
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


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_straight_edges_have_no_spare_nodes(glyph):
    """直線の上に、曲がり 1° 未満のオンカーブ点を置かない。"""
    resolved = load_resolved(glyph, "modern")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    for path in paths:
        assert all(turn >= 1.0 for turn in _line_line_turns(path))


def test_slash_maps_to_unicode_solidus(tmp_path: Path):
    """書き出したフォントの cmap は U+002F を slash にする。"""
    built = build_style("modern", glyphs=("H", "slash"), out_dir=tmp_path)
    cmap = TTFont(built["otf"]).getBestCmap()
    assert cmap[0x002F] == "slash"


@pytest.fixture(scope="module")
def compiled():
    root = Path(tempfile.mkdtemp())
    return build_style("modern", glyphs=_GLYPHS, out_dir=root)


def _design(glyph: str):
    resolved = load_resolved(glyph, "modern")
    return fit_outline(build_glyph(resolved), resolved.style)


@pytest.mark.parametrize("glyph", _GLYPHS)
def test_shipped_ttf_stays_on_the_design(compiled, glyph):
    """G-TT。TTF の最大 ≤ 1.0、平均は 0 以上 0.3 以下。"""
    worst, mean = outline_gap(_design(glyph), compiled["ttf"], glyph)
    assert worst <= 1.0
    assert 0.0 <= mean <= 0.3
