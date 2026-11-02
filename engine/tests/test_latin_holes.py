"""小さい穴は残し、入れ子の裂け目は落とす。"""

from __future__ import annotations

from engine.geometry import Vec2
from engine.latin.build import _HOLE_KEEP, _filter_contours


def _square(
    x: float, y: float, side: float, *, reverse: bool = False
) -> tuple[Vec2, ...]:
    points = (
        Vec2(x, y),
        Vec2(x + side, y),
        Vec2(x + side, y + side),
        Vec2(x, y + side),
    )
    return tuple(reversed(points)) if reverse else points


def test_small_counter_above_the_keep_floor_stays():
    """微小除去の床より小さくても、保護床以上の穴は残る。"""
    outer = _square(0, 0, 1000)
    hole = _square(100, 100, 55, reverse=True)
    assert abs(_area(hole)) > _HOLE_KEEP
    kept = _filter_contours((outer, hole), micro_floor=3500.0)
    assert len(kept) == 2


def test_nested_slit_above_the_keep_floor_goes():
    """穴の中の負輪郭は、保護床以上でも包含が偶数なら落とす。"""
    outer = _square(0, 0, 1000)
    hole = _square(200, 200, 400, reverse=True)
    slit = _square(300, 300, 60, reverse=True)
    assert abs(_area(slit)) > _HOLE_KEEP
    kept = _filter_contours((outer, hole, slit), micro_floor=2000.0)
    assert len(kept) == 2
    assert all(abs(_area(contour)) > 10000.0 for contour in kept)


def test_counter_on_the_keep_floor_stays_and_just_under_goes():
    """保護床ちょうどは残り、その直下の穴は落ちる。微小床が 0 でも同じ。"""
    outer = _square(0, 0, 1000)
    on_floor = _square(100, 100, 50, reverse=True)
    under = _square(400, 400, 49, reverse=True)
    assert abs(_area(on_floor)) == _HOLE_KEEP
    assert abs(_area(under)) < _HOLE_KEEP
    kept = _filter_contours((outer, on_floor, under), micro_floor=0.0)
    assert on_floor in kept
    assert under not in kept


def test_same_sign_speck_below_the_micro_floor_goes():
    """外形と同じ向きの小さい破片は、これまでどおり微小床で落とす。"""
    outer = _square(0, 0, 1000)
    speck = _square(100, 100, 10)
    kept = _filter_contours((outer, speck), micro_floor=400.0)
    assert kept == (outer,)


def _area(points: tuple[Vec2, ...]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:] + points[:1]):
        total += start.x * end.y - end.x * start.y
    return 0.5 * total
