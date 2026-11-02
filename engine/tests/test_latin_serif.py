"""クラシックのセリフ。ブラケットは下面と画の縁に接線でつながる凹の曲線で、長さと厚さは様式の値のまま。"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from engine.geometry import Vec2
from engine.latin import build
from engine.latin.build import build_glyph
from engine.latin.load import load_resolved
from engine.latin.outline import fit_outline


def _turn(prev: Vec2, point: Vec2, nxt: Vec2) -> float | None:
    d1, d2 = point - prev, nxt - point
    if d1.length() < 0.4 or d2.length() < 0.4:
        return None
    return abs(math.degrees(math.atan2(d1.cross(d2), d1.dot(d2))))


def _bracket_turns(points: list[Vec2], low: float, high: float, keep) -> list[float]:
    """low < y < high の点の折れ。幹の縁や板の端の直角（40° 超）は数えない。"""
    found = []
    for index, point in enumerate(points):
        if not low < point.y < high or not keep(point):
            continue
        turn = _turn(points[index - 1], point, points[(index + 1) % len(points)])
        if turn is None or turn > 40.0:
            continue
        found.append(turn)
    return found


def _serif(resolved) -> tuple[float, float, float]:
    cap = resolved.style.cap_height
    metrics = resolved.style.metrics
    return (
        metrics["serif_length"] * cap,
        max(metrics["serif_thick"] * cap, 1.0) * 1.35,
        metrics["bracket"] * cap,
    )


@pytest.mark.parametrize(("glyph", "ends"), (("H", ("foot", "top")), ("B", ("foot",))))
def test_classic_stem_brackets_have_no_corner(glyph, ends):
    """幹のセリフのブラケットは面取りの楔にせず、折れ 5° 以下の曲線でつなぐ。"""
    resolved = load_resolved(glyph, "classic")
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    _length, slab, reach = _serif(resolved)
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    points = list(outer)
    xs = [point.x for point in points]
    left_stem = min(xs) + 60.0
    keep = (lambda point: True) if glyph == "H" else (lambda point: point.x < left_stem)
    for end in ends:
        if end == "foot":
            low, high = slab - 0.4, slab + reach + 4.0
        else:
            low, high = cap - slab - reach - 4.0, cap - slab + 0.4
        turns = _bracket_turns(points, low, high, keep)
        assert len(turns) > 8
        assert max(turns) <= 5.0


def test_classic_stem_serif_keeps_length_and_thickness():
    """板の長さは serif_length、端の面の高さは serif_thick の 1.35 倍。差は 0.5 以内。"""
    resolved = load_resolved("H", "classic")
    outline = build_glyph(resolved)
    length, slab, _reach = _serif(resolved)
    outer = next(contour for contour, hole in zip(outline.contours, outline.holes) if not hole)
    points = list(outer)
    left = min(point.x for point in points)
    crossings = sorted(
        start.x + (end.x - start.x) * (1.0 - start.y) / (end.y - start.y)
        for start, end in pairwise([*points, points[0]])
        if (start.y - 1.0) * (end.y - 1.0) < 0.0
    )
    assert crossings[1] - crossings[0] == pytest.approx(length, abs=0.5)
    face = [
        (start, end)
        for start, end in pairwise([*points, points[0]])
        if abs(start.x - left) < 0.01 and abs(end.x - left) < 0.01 and start.y < 350.0
    ]
    height = max(max(start.y, end.y) for start, end in face) - min(
        min(start.y, end.y) for start, end in face
    )
    assert height == pytest.approx(slab, abs=0.5)


@pytest.mark.parametrize("glyph", ("H", "V"))
def test_classic_fitted_brackets_stay_curves(glyph):
    """当て直した後も、ブラケットを短い直線の並び（多角形）にしない。直線は 9 UPM 以上。"""
    resolved = load_resolved(glyph, "classic")
    fitted = fit_outline(build_glyph(resolved), resolved.style)
    lines = []
    for path in fitted:
        cur = path.start
        for seg in path.segs:
            end = (seg[1], seg[2]) if seg[0] == "L" else (seg[5], seg[6])
            if seg[0] == "L":
                lines.append(math.dist(cur, end))
            cur = end
    assert min(lines) >= 9.0


def _diagonal_serif(style: str):
    resolved = load_resolved("H", style)
    unit = Vec2(0.3, -1.0).normalized()
    origin = Vec2(300.0, 0.0)
    kind = resolved.style.terminals["foot"]
    return resolved, build._level_serif(origin, unit, 50.0, kind, resolved), origin, unit


@pytest.mark.parametrize("style", ("classic", "chic"))
def test_diagonal_serif_is_square_at_the_cut(style):
    """斜めの画のセリフは、下面が切り口と同じ水平、両端は垂直。平行四辺形にしない。"""
    resolved, polys, origin, _unit = _diagonal_serif(style)
    cap = resolved.style.cap_height
    slab = max(resolved.style.metrics["serif_thick"] * cap, 1.0) * 1.35
    plate = polys[0]
    assert len(plate) == 4
    xs = sorted({round(point.x, 6) for point in plate})
    ys = sorted({round(point.y, 6) for point in plate})
    assert len(xs) == 2
    assert ys == pytest.approx([origin.y, origin.y + slab])


def test_classic_diagonal_bracket_is_a_curve():
    """クラシックの斜めのセリフのブラケットは、両方の縁で折れ 5° 以下の曲線。"""
    _resolved, polys, _origin, _unit = _diagonal_serif("classic")
    fillets = polys[1:]
    assert len(fillets) == 2
    for fillet in fillets:
        curve = fillet[:-1]
        turns = [
            turn
            for prev, point, nxt in zip(curve, curve[1:], curve[2:], strict=False)
            if (turn := _turn(prev, point, nxt)) is not None
        ]
        assert len(turns) > 8
        assert max(turns) <= 5.0


def test_chic_diagonal_serif_has_no_wedge():
    """シックは下面と画の縁を角で会わせる。楔を足さない。"""
    _resolved, polys, _origin, _unit = _diagonal_serif("chic")
    assert len(polys) == 1
