"""K M N W は骨格と様式から同じ輪郭になる。build は字の名前で分岐しない。"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path

from engine.latin.build import build_glyph
from engine.latin.load import load_resolved
from engine.latin.outline import fit_outline
from engine.latin.schema import Knot

# リファクタ前のモダン。フィット後のオンカーブ点。±0.5 UPM。
_LOCKED = {
    "K": [
        (56.0000, 0.0000),
        (147.0000, 0.0000),
        (147.0000, 248.0000),
        (408.0000, 0.0000),
        (541.0000, 0.0000),
        (147.0000, 362.0000),
        (578.0000, 700.0000),
        (433.0000, 700.0000),
        (147.0000, 468.0000),
        (147.0000, 700.0000),
        (56.0000, 700.0000),
    ],
    "M": [
        (355.0000, -8.0000),
        (396.0000, -8.0000),
        (605.0000, 419.0000),
        (605.0000, 0.0000),
        (696.0000, 0.0000),
        (696.0000, 708.0000),
        (655.0000, 708.0000),
        (376.0000, 136.0000),
        (97.0000, 708.0000),
        (56.0000, 708.0000),
        (56.0000, 0.0000),
        (147.0000, 0.0000),
        (147.0000, 419.0000),
    ],
    "N": [
        (489.0000, -8.0000),
        (530.0000, -8.0000),
        (530.0000, 700.0000),
        (439.0000, 700.0000),
        (439.0000, 209.0000),
        (97.0000, 708.0000),
        (56.0000, 708.0000),
        (56.0000, 0.0000),
        (147.0000, 0.0000),
        (147.0000, 491.0000),
    ],
    "W": [
        (219.0000, -8.0000),
        (260.0000, -8.0000),
        (421.0000, 539.0000),
        (582.0000, -8.0000),
        (623.0000, -8.0000),
        (832.0000, 700.0000),
        (737.0000, 700.0000),
        (603.0000, 210.0000),
        (442.0000, 708.0000),
        (401.0000, 708.0000),
        (240.0000, 210.0000),
        (106.0000, 700.0000),
        (11.0000, 700.0000),
    ],
}

_SOURCES = (
    Path(__file__).resolve().parents[1] / "src" / "engine" / "latin" / "build.py",
    Path(__file__).resolve().parents[1] / "src" / "engine" / "latin" / "gate.py",
)
_GLYPH_BRANCH = (
    re.compile(r"glyph\s*(?:==|!=|in)\s*"),
    re.compile(r"""['\"][A-Z]['\"]\s*==\s*[^\n]{0,80}glyph"""),
    re.compile(r"""glyph[^\n]{0,60}==\s*['\"][A-Z]['\"]"""),
)


def _fitted(resolved):
    return fit_outline(build_glyph(resolved), resolved.style)[0].on_curve_points()


def _hausdorff(left, right) -> float:
    def directed(points, others) -> float:
        return max(min(math.hypot(x - u, y - v) for u, v in others) for x, y in points)

    return max(directed(left, right), directed(right, left))


def test_modern_kmnw_matches_the_locked_outlines():
    """リファクタ後も、フィットした K M N W は記録から 0.5 UPM 以内。"""
    for glyph, expect in _LOCKED.items():
        found = _fitted(load_resolved(glyph, "modern"))
        assert _hausdorff(found, expect) <= 0.5


def test_build_and_gate_do_not_branch_on_glyph_names():
    """字の名前で輪郭を分けない。"""
    for path in _SOURCES:
        source = path.read_text(encoding="utf-8")
        for pattern in _GLYPH_BRANCH:
            match = pattern.search(source)
            assert match is None, f"{path.name}: {match.group(0)!r}"


def _move_knot(resolved, stroke_id: str, index: int, x: float):
    strokes = []
    for stroke in resolved.skeleton.strokes:
        if stroke.id != stroke_id:
            strokes.append(stroke)
            continue
        knots = list(stroke.knots)
        knot = knots[index]
        knots[index] = Knot(x, knot.y, knot.kind, knot.angle_deg)
        strokes.append(replace(stroke, knots=tuple(knots)))
    return replace(
        resolved, skeleton=replace(resolved.skeleton, strokes=tuple(strokes))
    )


def _lowest_x(resolved) -> float:
    points = [point for contour in build_glyph(resolved).contours for point in contour]
    floor = min(point.y for point in points)
    low = [point.x for point in points if point.y < floor + 1.0]
    return sum(low) / len(low)


def _ink_width(resolved) -> float:
    points = [point for contour in build_glyph(resolved).contours for point in contour]
    xs = [point.x for point in points]
    return max(xs) - min(xs)


def test_m_valley_and_n_stem_follow_the_knots():
    """M の谷の節点と N の幹の x を動かすと、輪郭が動く。"""
    base = load_resolved("M", "modern")
    moved = _move_knot(_move_knot(base, "fall", 1, 0.38), "rise", 0, 0.38)
    assert abs(_lowest_x(moved) - _lowest_x(base)) > 1.0
    n = load_resolved("N", "modern")
    shifted = _move_knot(_move_knot(n, "left", 0, 0.26), "left", 1, 0.26)
    assert abs(_ink_width(shifted) - _ink_width(n)) > 1.0
