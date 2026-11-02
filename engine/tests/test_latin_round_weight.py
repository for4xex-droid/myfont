"""閉じた丸い字（O 0）は直線の幹より少し太い。B の碗、S の腕、幹は動かさない。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.latin.build import _stroke_resolved, build_glyph
from engine.latin.gate import _runs
from engine.latin.load import load_resolved


def _stem(style: str) -> float:
    outline = build_glyph(load_resolved("H", style))
    left, right = _runs(outline, 250.0, vertical=False)[0]
    return right - left


def _side(outline) -> float:
    """外形の右端（接線が垂直）の高さで、右の壁の幅。"""
    points = [
        point
        for contour, hole in zip(outline.contours, outline.holes, strict=True)
        if not hole
        for point in contour
    ]
    extreme = max(points, key=lambda point: point.x)
    left, right = _runs(outline, extreme.y, vertical=False)[-1]
    return right - left


def _crown(outline) -> float:
    """字の中央の縦の線で、上の壁の厚さ。"""
    xs = [point.x for contour in outline.contours for point in contour]
    # 中央の節点に当たると交点が重なり、厚さが 0 になる。半ユニット以内で避ける。
    mid = (min(xs) + max(xs)) / 2.0 + 0.123
    cuts = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            if (start.x - mid) * (end.x - mid) > 0.0 or start.x == end.x:
                continue
            t = (mid - start.x) / (end.x - start.x)
            cuts.append(start.y + (end.y - start.y) * t)
    cuts.sort()
    return cuts[-1] - cuts[-2]


@pytest.mark.parametrize("style", ("modern", "pop"))
@pytest.mark.parametrize("glyph", ("O", "zero"))
def test_mono_round_is_a_little_heavier_than_the_stem(style, glyph):
    outline = build_glyph(load_resolved(glyph, style))
    stem = _stem(style)
    for wall in (_side(outline), _crown(outline)):
        assert 1.015 <= wall / stem <= 1.025


@pytest.mark.parametrize("glyph", ("O", "zero"))
def test_chic_round_thickens_only_the_thick_side(glyph):
    resolved = load_resolved(glyph, "chic")
    outline = build_glyph(resolved)
    assert 1.015 <= _side(outline) / _stem("chic") <= 1.025
    hairline = resolved.pen.hairline * resolved.style.cap_height
    assert _crown(outline) == pytest.approx(hairline, abs=0.5)


@pytest.mark.parametrize("style", ("modern", "classic", "chic", "pop"))
def test_only_closed_free_bowls_take_the_round_pen(style):
    o = load_resolved("O", style)
    bowl = _stroke_resolved(o.skeleton.strokes[0], o)
    assert bowl.pen.stem > o.pen.stem
    if o.pen.type == "mono":
        assert bowl.pen.hairline == pytest.approx(bowl.pen.stem)
    else:
        assert bowl.pen.hairline == o.pen.hairline
    for glyph in ("B", "H", "S"):
        other = load_resolved(glyph, style)
        for stroke in other.skeleton.strokes:
            assert _stroke_resolved(stroke, other).pen == other.pen


@pytest.mark.parametrize("glyph", ("O", "zero", "S"))
def test_pop_round_overshoots_for_its_weight(glyph):
    # 太い丸ほど大きく要る。2026-10-07 のポップは幹 154 に対して 8 だった。
    resolved = load_resolved(glyph, "pop")
    outline = build_glyph(resolved)
    cap = resolved.style.cap_height
    over = resolved.style.overshoot["round"] * cap
    ys = [
        point.y
        for contour, hole in zip(outline.contours, outline.holes, strict=True)
        if not hole
        for point in contour
    ]
    assert max(ys) - cap == pytest.approx(over, abs=0.5)
    assert -min(ys) == pytest.approx(over, abs=0.5)


def test_round_pen_follows_the_group_scalar():
    o = load_resolved("O", "modern")
    groups = {"round": {"bowl_ratio": 1.10}}
    plain = replace(o, style=replace(o.style, groups=groups))
    bowl = _stroke_resolved(o.skeleton.strokes[0], plain)
    assert bowl.pen.stem == pytest.approx(o.pen.stem * 1.10)
    assert bowl.pen.hairline == pytest.approx(bowl.pen.stem)


@pytest.mark.parametrize("ratio", (0.0, -1.0))
def test_nonpositive_bowl_ratio_is_rejected(ratio):
    o = load_resolved("O", "modern")
    plain = replace(o, style=replace(o.style, groups={"round": {"bowl_ratio": ratio}}))
    with pytest.raises(ValueError, match="bowl_ratio"):
        _stroke_resolved(o.skeleton.strokes[0], plain)
