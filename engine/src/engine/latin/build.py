"""1字を骨格から塗り輪郭へ。内部座標は Y 上向き、UPM 1000。"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from pathops import Path, PathOp, op, simplify

from engine.geometry import (
    Vec2,
    sample_cubic,
    variable_width_outline,
    variable_width_ring_outlines,
)
from engine.join_solver import (
    contour_points,
    count_contours,
    pathops_union,
    poly_to_path,
    split_contours,
)
from engine.latin.hobby import Cubic, expand_stroke
from engine.latin.joins import (
    bevel_apex_valley,
    retract_end,
    smooth_side_pinches,
    taper_end,
    trim_apex_stub,
)
from engine.latin.load import Resolved
from engine.latin.pens import half_width
from engine.latin.schema import Knot, Stroke
from engine.latin.terminals import terminal_polygon

_SAMPLES = 24


@dataclass(frozen=True)
class GlyphOutline:
    glyph: str
    advance: float
    contours: tuple[tuple[Vec2, ...], ...]
    holes: tuple[bool, ...]

    @property
    def contour_count(self) -> int:
        return len(self.contours)

    @property
    def hole_count(self) -> int:
        return sum(self.holes)


def _signed_area(points: tuple[Vec2, ...]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i].x * points[j].y - points[j].x * points[i].y
    return 0.5 * area


def _nudge_apex(stroke: Stroke, apex: float) -> Stroke:
    knots = list(stroke.knots)

    def nudge(index: int, other: int) -> None:
        knot = knots[index]
        dy = -apex if knot.y <= knots[other].y else apex
        knots[index] = Knot(knot.x, knot.y + dy, knot.kind, knot.angle_deg)

    if stroke.ends[0] == "apex" and len(knots) >= 2:
        nudge(0, 1)
    if stroke.ends[1] == "apex" and len(knots) >= 2:
        nudge(len(knots) - 1, len(knots) - 2)
    return replace(stroke, knots=tuple(knots))


def _font_map(stroke: Stroke, resolved: Resolved):
    """節点をフォント空間へ。閉じた字は単位正方形で展開してからこの写像を掛ける。"""
    style = resolved.style
    width = style.proportions[resolved.skeleton.glyph] * style.cap_height
    left = style.sidebearing["base"] * style.cap_height * style.sidebearing[resolved.skeleton.sides[0]]
    overshoot = style.overshoot["round"] * style.cap_height if stroke.role == "bowl" else 0.0
    span = style.cap_height + 2.0 * overshoot

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        return (left + point[0] * width, point[1] * span - overshoot)

    return xy


def _place(stroke: Stroke, resolved: Resolved):
    prepared = _nudge_apex(stroke, resolved.style.overshoot["apex"])
    xy = _font_map(prepared, resolved)
    if stroke.closed:
        # 閉じた4極は単位正方形で円にし、写像で楕円にする。
        cubics = expand_stroke(prepared)
        placed = tuple(Cubic(xy(c.p0), xy(c.c1), xy(c.c2), xy(c.p1)) for c in cubics)
        return prepared, placed
    # 開いた曲線は、縦横の縮尺が違ったあとの角度で Hobby を解く。
    knots = tuple(Knot(xy((k.x, k.y))[0], xy((k.x, k.y))[1], k.kind, k.angle_deg) for k in prepared.knots)
    return replace(prepared, knots=knots), expand_stroke(replace(prepared, knots=knots))


def _sample(cubics) -> list[tuple[Vec2, Vec2]]:
    samples: list[tuple[Vec2, Vec2]] = []
    for cubic in cubics:
        seg = sample_cubic(Vec2(*cubic.p0), Vec2(*cubic.c1), Vec2(*cubic.c2), Vec2(*cubic.p1), n=_SAMPLES)
        if samples:
            seg = seg[1:]
        samples.extend(seg)
    return samples


def _widths(samples: list[tuple[Vec2, Vec2]], resolved: Resolved, stroke: Stroke) -> list[float]:
    cap = resolved.style.cap_height
    widths: list[float] = []
    for _pos, tangent in samples:
        angle = math.atan2(tangent.y, tangent.x)
        widths.append(half_width(resolved.pen, stroke.role, angle) * cap)
    factor = resolved.style.joins["crotch_thin"]
    ends = {stroke.ends[0], stroke.ends[1]}
    crotch = any(join.type == "crotch" and stroke.id in (join.a, join.b) for join in resolved.skeleton.joins)
    if crotch and "apex" not in ends:
        if stroke.ends[0] != "none":
            taper_end(widths, at_start=True, factor=factor)
        if stroke.ends[1] != "none":
            taper_end(widths, at_start=False, factor=factor)
    return widths


def _to_path(poly: list[Vec2]) -> Path:
    path = poly_to_path(poly)
    if count_contours(path) == 0:
        return path
    return simplify(path, fix_winding=True)


def _difference(outer: Path, inner: Path) -> Path:
    return op(outer, inner, PathOp.DIFFERENCE)


def _union_all(paths: list[Path]) -> Path:
    kept = [path for path in paths if count_contours(path)]
    if not kept:
        return Path()
    return pathops_union(kept)


def _terminal_paths(samples: list[tuple[Vec2, Vec2]], widths: list[float], stroke: Stroke, resolved: Resolved) -> list[Path]:
    style = resolved.style
    metrics = style.metrics
    length = metrics.get("serif_length", 0.12) * style.cap_height
    thick = metrics.get("serif_thick", 0.02) * style.cap_height
    paths: list[Path] = []
    ends = ((0, -1.0, stroke.ends[0]), (len(samples) - 1, 1.0, stroke.ends[1]))
    for index, sign, tag in ends:
        kind = style.terminals[tag]
        origin, tangent = samples[index]
        outward = tangent * sign
        poly = terminal_polygon(
            kind,
            origin,
            outward,
            widths[index],
            serif_length=length,
            serif_thick=thick,
            round_frac=metrics.get("round_frac", 1.0),
            bracket=metrics.get("bracket", 0.0) * style.cap_height,
        )
        if poly:
            paths.append(_to_path(poly))
    return paths


def _centerline(stroke: Stroke, resolved: Resolved) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    _prepared, cubics = _place(stroke, resolved)
    samples = _sample(cubics)
    if len(samples) < 2:
        return [], []
    return samples, _widths(samples, resolved, stroke)


def _apply_joins(
    samples: dict[str, list[tuple[Vec2, Vec2]]],
    widths: dict[str, list[float]],
    resolved: Resolved,
) -> None:
    """接合の a 側の端を、b の中心線まで戻す。幹の端は削らない。"""
    for join in resolved.skeleton.joins:
        if join.type not in ("bowl_join", "T", "L"):
            continue
        if join.a not in samples or join.b not in samples:
            continue
        _bury(samples, widths, join.a, join.b)


def _bury(
    samples: dict[str, list[tuple[Vec2, Vec2]]],
    widths: dict[str, list[float]],
    joiner: str,
    partner: str,
) -> None:
    cur_s, cur_w = samples[joiner], widths[joiner]
    for at_start in (True, False):
        cur_s, cur_w = retract_end(cur_s, cur_w, samples[partner], widths[partner], at_start=at_start)
    samples[joiner] = cur_s
    widths[joiner] = cur_w


def _stroke_paths(
    stroke: Stroke,
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    resolved: Resolved,
) -> list[Path]:
    if len(samples) < 2:
        return []
    paths: list[Path] = []
    if stroke.closed:
        outer, inner = variable_width_ring_outlines(samples, widths)
        outer_path = _to_path(outer)
        inner_path = _to_path(inner)
        if count_contours(inner_path):
            paths.append(_difference(outer_path, inner_path))
        else:
            paths.append(outer_path)
    else:
        paths.append(_to_path(variable_width_outline(samples, widths, close=True)))
    paths.extend(_terminal_paths(samples, widths, stroke, resolved))
    return paths


def build_glyph(resolved: Resolved) -> GlyphOutline:
    strokes = resolved.skeleton.strokes
    samples: dict[str, list[tuple[Vec2, Vec2]]] = {}
    widths: dict[str, list[float]] = {}
    for stroke in strokes:
        samples[stroke.id], widths[stroke.id] = _centerline(stroke, resolved)
    _apply_joins(samples, widths, resolved)
    paths = [
        path
        for stroke in strokes
        for path in _stroke_paths(stroke, samples[stroke.id], widths[stroke.id], resolved)
    ]
    united = _union_all(paths)
    raw = [tuple(Vec2(x, y) for x, y in contour_points(c)) for c in split_contours(united)]
    floor = resolved.style.micro_area_floor
    raw = tuple(c for c in raw if len(c) >= 3 and abs(_signed_area(c)) >= floor)
    if not raw:
        raise ValueError(f"{resolved.skeleton.glyph}: empty outline")
    largest = max(range(len(raw)), key=lambda i: abs(_signed_area(raw[i])))
    sign = 1.0 if _signed_area(raw[largest]) >= 0.0 else -1.0
    holes = tuple(_signed_area(c) * sign < 0.0 for c in raw)
    raw = tuple(
        tuple(smooth_side_pinches(trim_apex_stub(bevel_apex_valley(list(contour))))) if not hole else contour
        for contour, hole in zip(raw, holes)
    )
    style = resolved.style
    width = style.proportions[resolved.skeleton.glyph] * style.cap_height
    right = style.sidebearing["base"] * style.cap_height * style.sidebearing[resolved.skeleton.sides[1]]
    left = style.sidebearing["base"] * style.cap_height * style.sidebearing[resolved.skeleton.sides[0]]
    return GlyphOutline(resolved.skeleton.glyph, left + width + right, raw, holes)
