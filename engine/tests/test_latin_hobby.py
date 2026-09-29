"""工程2 G-H: 直線・角・円の極・同じ入力。"""

from __future__ import annotations

import math

from engine.latin.hobby import expand_stroke
from engine.latin.schema import Knot, Stroke


def _stroke(knots, *, closed=False, role="thick"):
    return Stroke("s", tuple(knots), closed, role, ("none", "none"), 1.0, None)


def _out(cubic):
    return math.atan2(cubic.c1[1] - cubic.p0[1], cubic.c1[0] - cubic.p0[0])


def _inn(cubic):
    return math.atan2(cubic.p1[1] - cubic.c2[1], cubic.p1[0] - cubic.c2[0])


def _axis(angle: float) -> bool:
    snapped = round(angle / (math.pi / 2.0)) * (math.pi / 2.0)
    delta = (angle - snapped + math.pi) % (2.0 * math.pi) - math.pi
    return abs(delta) < 1e-6


def _collinear(cubic) -> bool:
    def cross(ax, ay, bx, by):
        return ax * by - ay * bx

    dx, dy = cubic.p1[0] - cubic.p0[0], cubic.p1[1] - cubic.p0[1]
    c1 = cross(cubic.c1[0] - cubic.p0[0], cubic.c1[1] - cubic.p0[1], dx, dy)
    c2 = cross(cubic.c2[0] - cubic.p0[0], cubic.c2[1] - cubic.p0[1], dx, dy)
    return abs(c1) < 1e-9 and abs(c2) < 1e-9


def test_line_segment_is_straight():
    stroke = _stroke([Knot(0.0, 0.0, "line"), Knot(1.0, 0.2, "line")])
    assert _collinear(expand_stroke(stroke)[0])


def test_corner_breaks_the_tangent():
    stroke = _stroke(
        [Knot(0.0, 0.0, "smooth"), Knot(1.0, 0.0, "corner"), Knot(1.0, 1.0, "smooth")],
    )
    cubics = expand_stroke(stroke)
    turn = (_inn(cubics[0]) - _out(cubics[1]) + math.pi) % (2.0 * math.pi) - math.pi
    assert abs(turn) > math.radians(20)


def test_circle_poles_are_axis_aligned():
    poles = [
        Knot(0.5, 0.0, "smooth"),
        Knot(1.0, 0.5, "smooth"),
        Knot(0.5, 1.0, "smooth"),
        Knot(0.0, 0.5, "smooth"),
    ]
    cubics = expand_stroke(_stroke(poles, closed=True, role="bowl"))
    assert len(cubics) == 4
    assert all(_axis(_out(cubic)) for cubic in cubics)


def test_same_input_returns_the_same_cubics():
    poles = [
        Knot(0.5, 0.0, "smooth"),
        Knot(1.0, 0.5, "smooth"),
        Knot(0.5, 1.0, "smooth"),
        Knot(0.0, 0.5, "smooth"),
    ]
    stroke = _stroke(poles, closed=True, role="bowl")
    assert expand_stroke(stroke) == expand_stroke(stroke)


def test_open_collinear_knots_stay_on_the_chord():
    stroke = _stroke(
        [Knot(0.0, 0.5, "smooth"), Knot(0.5, 0.5, "smooth"), Knot(1.0, 0.5, "smooth")],
    )
    for cubic in expand_stroke(stroke):
        assert abs(_out(cubic)) < 1e-6
        assert abs(_inn(cubic)) < 1e-6
