"""1字を骨格から塗り輪郭へ。内部座標は Y 上向き、UPM 1000。"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from itertools import pairwise

from pathops import Path, PathOp, op, simplify

from engine.geometry import (
    UPM,
    Vec2,
    limit_half_to_curvature,
    sample_cubic,
    variable_width_outline,
    variable_width_ring_outlines,
)
from engine.join_solver import (
    HOLE_KEEP_UPM_AREA_RATIO,
    contour_points,
    count_contours,
    pathops_union,
    poly_to_path,
    split_contours,
)
from engine.latin.bowls import (
    box_ellipse,
    contrast_polygon,
    ease_outer_cusp,
    pen_envelope,
)
from engine.latin.hobby import Cubic, expand_stroke
from engine.latin.joins import (
    arc_open_crown,
    bevel_apex_valley,
    blunt_inner_peak,
    ease_level_shoulders,
    fair_bar_joins,
    fill_crown_saddle,
    fillet_bowl_waist,
    retract_end,
    smooth_side_pinches,
    trim_apex_stub,
)
from engine.latin.load import Resolved
from engine.latin.pens import half_width
from engine.latin.schema import Knot, Stroke
from engine.latin.terminals import Beak, terminal_polygon

_SAMPLES = 96


@dataclass(frozen=True)
class GlyphOutline:
    glyph: str
    advance: float
    contours: tuple[tuple[Vec2, ...], ...]
    holes: tuple[bool, ...]
    # 当て直しのあと、節点で接線と曲がりを揃える。くちばしの端を持つ字（S）だけ。
    fair: bool = False

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


# 端物の巻きくず（約 2400 まで）より上で、この帯の穴は残す。
_HOLE_KEEP = HOLE_KEEP_UPM_AREA_RATIO * UPM * UPM


def _inside(x: float, y: float, contour: tuple[Vec2, ...]) -> bool:
    inside = False
    previous = contour[-1]
    for point in contour:
        if (previous.y > y) != (point.y > y) and x < (point.x - previous.x) * (
            y - previous.y
        ) / (point.y - previous.y + 1e-15) + previous.x:
            inside = not inside
        previous = point
    return inside


def _interior(contour: tuple[Vec2, ...]) -> tuple[float, float]:
    count = len(contour)
    cx = sum(point.x for point in contour) / count
    cy = sum(point.y for point in contour) / count
    if _inside(cx, cy, contour):
        return cx, cy
    sign = 1.0 if _signed_area(contour) >= 0.0 else -1.0
    for start, end in pairwise(contour + contour[:1]):
        length = math.hypot(end.x - start.x, end.y - start.y)
        if length < 1e-12:
            continue
        nx = -(end.y - start.y) / length * sign
        ny = (end.x - start.x) / length * sign
        mx = (start.x + end.x) / 2.0
        my = (start.y + end.y) / 2.0
        for dist in (2.0, 5.0, 10.0, 20.0, 40.0):
            px, py = mx + nx * dist, my + ny * dist
            if _inside(px, py, contour):
                return px, py
    return cx, cy


def _depths(contours: tuple[tuple[Vec2, ...], ...]) -> list[int]:
    areas = [abs(_signed_area(contour)) for contour in contours]
    found: list[int] = []
    for index, contour in enumerate(contours):
        if len(contour) < 3:
            found.append(0)
            continue
        px, py = _interior(contour)
        depth = 0
        for other, area in zip(contours, areas):
            if other is contour or len(other) < 3 or area <= areas[index] + 1e-6:
                continue
            if _inside(px, py, other):
                depth += 1
        found.append(depth)
    return found


def _filter_contours(
    contours: tuple[tuple[Vec2, ...], ...], micro_floor: float
) -> tuple[tuple[Vec2, ...], ...]:
    """負輪郭は、包含が奇数で保護床以上のときだけ残す。外形は微小床で落とす。"""
    if not contours:
        return contours
    depths = _depths(contours)
    largest = max(range(len(contours)), key=lambda i: abs(_signed_area(contours[i])))
    outer_sign = 1.0 if _signed_area(contours[largest]) >= 0.0 else -1.0
    kept: list[tuple[Vec2, ...]] = []
    for contour, depth in zip(contours, depths):
        if len(contour) < 3:
            continue
        area = abs(_signed_area(contour))
        sign = 1.0 if _signed_area(contour) >= 0.0 else -1.0
        if sign != outer_sign:
            if depth % 2 == 1 and area >= _HOLE_KEEP:
                kept.append(contour)
            continue
        if contour is contours[largest] or area >= micro_floor:
            kept.append(contour)
    return tuple(kept)


def _nudge_apex(stroke: Stroke, resolved: Resolved) -> Stroke:
    """先端をオーバーシュートの分だけ外へ出す。丸い先端は丸の外側がそこに来るよう、真上（真下）へ戻す。"""
    style = resolved.style
    cap = style.cap_height
    width = style.proportions[resolved.skeleton.glyph] * cap
    apex = style.overshoot["apex"]
    kind = style.terminals["apex"]
    knots = list(stroke.knots)

    def nudge(index: int, other: int) -> None:
        knot = knots[index]
        reach = apex
        if kind in ("round", "ball"):
            angle = math.atan2(
                (knot.y - knots[other].y) * cap, (knot.x - knots[other].x) * width
            )
            reach -= (
                _round_radius(
                    kind, half_width(resolved.pen, stroke.role, angle) * cap, resolved
                )
                / cap
            )
        dy = -reach if knot.y <= knots[other].y else reach
        knots[index] = Knot(knot.x, knot.y + dy, knot.kind, knot.angle_deg)

    if stroke.ends[0] == "apex" and len(knots) >= 2:
        nudge(0, 1)
    if stroke.ends[1] == "apex" and len(knots) >= 2:
        nudge(len(knots) - 1, len(knots) - 2)
    return replace(stroke, knots=tuple(knots))


def _bowl_joined(stroke: Stroke, resolved: Resolved) -> bool:
    return any(
        join.type == "bowl_join" and join.a == stroke.id
        for join in resolved.skeleton.joins
    )


def _bowl_overshoot(stroke: Stroke, resolved: Resolved) -> float:
    """接合した碗は天地を平らなままにする。開いた碗だけ丸のオーバーシュート。"""
    if stroke.role != "bowl" or _bowl_joined(stroke, resolved):
        return 0.0
    return resolved.style.overshoot["round"] * resolved.style.cap_height


def _foot_sides(stroke: Stroke) -> set[str]:
    """足の端が天か地か。その側の外形は基準線に合わせ、オーバーシュートしない。"""
    found: set[str] = set()
    for index, tag in ((0, stroke.ends[0]), (-1, stroke.ends[1])):
        if tag != "foot":
            continue
        found.add("top" if stroke.knots[index].y >= 0.5 else "bottom")
    return found


def _stroke_resolved(stroke: Stroke, resolved: Resolved) -> Resolved:
    """幹に接合しない閉じた碗（O 0）だけ、グループの bowl_ratio で幹の太さを上げる。

    丸は同じ太さの直線より細く見える。ヘアラインは変えないので、nib では太い方向だけ太る。
    mono は hairline を stem と同じにして作る。幹だけ動かすと、その関係が壊れる。
    B の碗は幹と横画に挟まれて混むので入れない。
    クラシックの S は天の位置と穴の膝が検査の際にあり、1% 太らせても膝が 0.011 を超える。
    """
    if stroke.role != "bowl" or not stroke.closed or _bowl_joined(stroke, resolved):
        return resolved
    ratio = 1.0
    for name in resolved.skeleton.groups:
        ratio *= resolved.style.groups.get(name, {}).get("bowl_ratio", 1.0)
    if ratio == 1.0:
        return resolved
    if ratio <= 0.0:
        raise ValueError(
            f"{resolved.skeleton.glyph}: bowl_ratio {ratio} must be positive"
        )
    stem = resolved.pen.stem * ratio
    hairline = stem if resolved.pen.type == "mono" else resolved.pen.hairline
    pen = replace(resolved.pen, stem=stem, hairline=hairline)
    return replace(resolved, pen=pen)


@dataclass(frozen=True)
class _Frame:
    """節点空間からフォント空間への軸ごとの一次写像。"""

    x_off: float
    x_scale: float
    y_off: float
    y_scale: float

    def __call__(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            self.x_off + point[0] * self.x_scale,
            self.y_off + point[1] * self.y_scale,
        )


def _plain_frame(stroke: Stroke, resolved: Resolved) -> _Frame:
    style = resolved.style
    cap = style.cap_height
    width = style.proportions[resolved.skeleton.glyph] * cap
    left = (
        style.sidebearing["base"] * cap * style.sidebearing[resolved.skeleton.sides[0]]
    )
    overshoot = _bowl_overshoot(stroke, resolved)
    return _Frame(left, width, -overshoot, cap + 2.0 * overshoot)


def _place(stroke: Stroke, resolved: Resolved, frame: _Frame | None = None):
    prepared = _nudge_apex(stroke, resolved)
    xy = frame or _plain_frame(prepared, resolved)
    if stroke.closed:
        # 閉じた4極は単位正方形で円にし、写像で楕円にする。
        cubics = expand_stroke(prepared)
        placed = tuple(Cubic(xy(c.p0), xy(c.c1), xy(c.c2), xy(c.p1)) for c in cubics)
        return prepared, placed
    # 開いた曲線は、縦横の縮尺が違ったあとの角度で Hobby を解く。
    knots = tuple(
        Knot(xy((k.x, k.y))[0], xy((k.x, k.y))[1], k.kind, k.angle_deg)
        for k in prepared.knots
    )
    return replace(prepared, knots=knots), expand_stroke(replace(prepared, knots=knots))


def _sample(cubics) -> list[tuple[Vec2, Vec2]]:
    samples: list[tuple[Vec2, Vec2]] = []
    for cubic in cubics:
        seg = sample_cubic(
            Vec2(*cubic.p0),
            Vec2(*cubic.c1),
            Vec2(*cubic.c2),
            Vec2(*cubic.p1),
            n=_SAMPLES,
        )
        if samples:
            seg = seg[1:]
        samples.extend(seg)
    return samples


def _widths(
    samples: list[tuple[Vec2, Vec2]], resolved: Resolved, stroke: Stroke
) -> list[float]:
    cap = resolved.style.cap_height
    widths: list[float] = []
    slant = None
    if stroke.role == "slant_thin":
        if "slant_thin" not in resolved.style.metrics:
            raise ValueError(f"{resolved.skeleton.glyph}: metrics.slant_thin required")
        slant = float(resolved.style.metrics["slant_thin"])
    for _pos, tangent in samples:
        angle = math.atan2(tangent.y, tangent.x)
        widths.append(
            half_width(resolved.pen, stroke.role, angle, slant_ratio=slant) * cap
        )
    ends = {stroke.ends[0], stroke.ends[1]}
    if "apex" not in ends:
        _crotch_taper(samples, widths, stroke, resolved)
    if ends == {"open"} and resolved.style.terminals["open"] == "beak":
        metrics = resolved.style.metrics
        if "spine_weight" in metrics:
            _hold_spine(samples, widths, resolved.pen.stem * cap / 2.0, metrics["spine_weight"])
        if "spine_smooth" in metrics:
            widths = _smooth_along(samples, widths, metrics["spine_smooth"] * cap)
    return limit_half_to_curvature(samples, widths)


def _crotch_taper(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> None:
    """股の端を細い端にして、半幅を弧長に対して一次で変える。

    hw(s) = hw0 × (1 − (1 − t) · s / L)。s = 0 が太い端。
    端が none ならその端が細い。両端を細くするときは、全長を t 倍の一定幅にする。
    中央で折り返すと縁が折れるので、先細りは片側だけ。接合の a 側だけを細める。
    """
    factor = resolved.style.joins["crotch_thin"]
    if factor == 1.0 or len(widths) < 2:
        return
    joined = any(
        join.type == "crotch" and join.a == stroke.id
        for join in resolved.skeleton.joins
    )
    if not joined:
        return
    both_feet = stroke.ends == ("foot", "foot")
    thin_start = stroke.ends[0] == "none" or both_feet
    thin_end = stroke.ends[1] == "none" or both_feet
    if not thin_start and not thin_end:
        return
    if thin_start and thin_end:
        for index in range(len(widths)):
            widths[index] *= factor
        return
    lengths = [0.0]
    for prev, cur in pairwise(samples):
        lengths.append(lengths[-1] + (cur[0] - prev[0]).length())
    total = lengths[-1] or 1.0
    for index, distance in enumerate(lengths):
        along = distance / total
        if thin_start:
            scale = factor + (1.0 - factor) * along
        else:
            scale = 1.0 - (1.0 - factor) * along
        widths[index] *= scale


def _hold_spine(
    samples: list[tuple[Vec2, Vec2]], widths: list[float], stem_half: float, weight: float
) -> None:
    """上の碗の左端から下の碗の右端まで（接線の x が負から正、正から負へ変わる間）を、
    幹の半幅 × (1 + (weight − 1) sin πu) より細くしない。ペン角 0 の斜めの背が細るのを止める。"""
    xs = [tangent.x for _pos, tangent in samples]
    start = next((i for i in range(1, len(xs)) if xs[i - 1] < 0.0 <= xs[i]), None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(xs)) if xs[i - 1] > 0.0 >= xs[i]), None)
    if end is None:
        return
    for i in range(start, end + 1):
        u = (i - start) / (end - start)
        widths[i] = max(widths[i], stem_half * (1.0 + (weight - 1.0) * math.sin(math.pi * u)))


def _smooth_along(
    samples: list[tuple[Vec2, Vec2]], widths: list[float], sigma: float
) -> list[float]:
    """半幅を弧の長さのガウスで均す。点の番号で均すと、節点で点の間隔が飛んで角ができる。
    端の外は端の値が続くとみなす（端で細らない）。"""
    if sigma <= 0.0 or len(widths) < 3:
        return widths
    arc = [0.0]
    for (a, _ta), (b, _tb) in pairwise(samples):
        arc.append(arc[-1] + (b - a).length())
    n = len(widths)
    ds = [(arc[min(n - 1, k + 1)] - arc[max(0, k - 1)]) / 2.0 for k in range(n)]
    reach = 3.0 * sigma
    out: list[float] = []
    for i in range(n):
        acc = total = 0.0
        for k in range(n):
            dist = arc[k] - arc[i]
            if abs(dist) > reach:
                continue
            weight = math.exp(-0.5 * (dist / sigma) ** 2) * ds[k]
            acc += widths[k] * weight
            total += weight
        for value, start, stop in (
            (widths[0], arc[i] - reach, 0.0),
            (widths[-1], arc[-1], arc[i] + reach),
        ):
            for j in range(int(max(0.0, stop - start))):
                weight = math.exp(-0.5 * ((start + j + 0.5 - arc[i]) / sigma) ** 2)
                acc += value * weight
                total += weight
        out.append(acc / total)
    return out


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


def _terminal_paths(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
    *,
    skip: set[int] | None = None,
) -> list[Path]:
    style = resolved.style
    metrics = style.metrics
    length = metrics.get("serif_length", 0.12) * style.cap_height
    thick = metrics.get("serif_thick", 0.02) * style.cap_height
    beak = None
    if "beak_drop" in metrics:
        cap = style.cap_height
        beak = Beak(
            drop=metrics["beak_drop"] * cap,
            thick=thick,
            bracket=metrics.get("beak_bracket", 0.0) * cap,
            sweep=metrics.get("beak_sweep", 0.0) * cap,
            tip=metrics.get("beak_tip", 0.0) * cap,
        )
    paths: list[Path] = []
    ends = ((0, -1.0, stroke.ends[0]), (len(samples) - 1, 1.0, stroke.ends[1]))
    for index, sign, tag in ends:
        if skip and index in skip:
            continue
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
            samples=samples,
            widths=widths,
            index=index,
            beak=beak,
        )
        if poly:
            paths.append(_to_path(poly))
    return paths


def _trim(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    distance: float,
    *,
    at_start: bool,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    """端から弧長 distance を切り落とす。"""
    if distance <= 0.0 or len(samples) < 2:
        return samples, widths
    pts = list(samples) if not at_start else list(reversed(samples))
    ws = list(widths) if not at_start else list(reversed(widths))
    left = distance
    while len(pts) >= 2:
        end, tangent = pts[-1]
        prev = pts[-2][0]
        seg = (end - prev).length()
        if seg >= left:
            t = 1.0 - left / seg if seg > 1e-9 else 0.0
            pts[-1] = (prev + (end - prev) * t, tangent)
            break
        left -= seg
        pts.pop()
        ws.pop()
    if len(pts) < 2:
        return samples, widths
    if at_start:
        pts.reverse()
        ws.reverse()
    return pts, ws


def _round_radius(kind: str, half: float, resolved: Resolved) -> float:
    if kind == "ball":
        return half * 1.15
    if kind == "round":
        return half + half * max(
            0.0, resolved.style.metrics.get("round_frac", 1.0) - 1.0
        )
    return 0.0


def _tuck_round_ends(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    """丸い端は、丸の外側が元の端の位置に来るまで中心線を縮める。"""
    if stroke.closed:
        return samples, widths
    for at_start, tag in ((True, stroke.ends[0]), (False, stroke.ends[1])):
        kind = resolved.style.terminals[tag]
        if kind not in ("round", "ball") or tag == "apex" or len(samples) < 2:
            continue
        index = 0 if at_start else -1
        radius = _round_radius(kind, widths[index], resolved)
        unit = samples[index][1].normalized()
        lead = max(abs(unit.x), abs(unit.y), 1e-6)
        samples, widths = _trim(samples, widths, radius / lead, at_start=at_start)
    return samples, widths


def _centerline(
    stroke: Stroke,
    resolved: Resolved,
    frame: _Frame | None = None,
    *,
    hug: bool = True,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    _prepared, cubics = _place(stroke, resolved, frame)
    samples = _sample(cubics)
    if len(samples) < 2:
        return [], []
    widths = _widths(samples, resolved, stroke)
    # 抱き込みは、外形を基準線に合わせる計測にだけ使う。nib の碗の塗りは断面から描く。
    if hug and stroke.role == "bowl" and _bowl_joined(stroke, resolved):
        samples, widths = _hug_outer(samples, widths, _serif_bar_half(resolved))
    return _tuck_round_ends(samples, widths, stroke, resolved)


def _serif_bar_half(resolved: Resolved) -> float:
    """セリフの下面まで届く、横棒の半幅。セリフがない様式は 0。"""
    if resolved.style.terminals.get("foot") not in _SERIF_KINDS:
        return 0.0
    thick = max(
        resolved.style.metrics.get("serif_thick", 0.02) * resolved.style.cap_height, 1.0
    )
    return thick * 1.35 / 2.0


def _hug_outer(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    bar_half: float,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    """外の輪郭を一番細い所にそろえ、それ以上の太さは内側へ逃がす。

    水平に近い所は、セリフの下面より細いと段になるので、内側だけそこまで太くする。
    """
    if len(samples) < 3:
        return samples, widths
    area = 0.0
    pts = [pos for pos, _tangent in samples]
    for start, end in zip(pts, pts[1:] + pts[:1]):
        area += start.x * end.y - end.x * start.y
    if abs(area) < 1.0:
        return samples, widths
    outward = 1.0 if area > 0.0 else -1.0
    thinnest = min(widths)
    moved: list[tuple[Vec2, Vec2]] = []
    widened: list[float] = []
    for (pos, tangent), half in zip(samples, widths):
        length = tangent.length()
        if length < 1e-9:
            moved.append((pos, tangent))
            widened.append(half)
            continue
        inward = Vec2(-tangent.y / length, tangent.x / length) * outward
        level = abs(tangent.y) < abs(tangent.x) * 0.08
        target = max(half, bar_half) if level else half
        extra = target - thinnest
        if extra < 0.5:
            moved.append((pos, tangent))
            widened.append(half)
            continue
        moved.append((pos + inward * extra, tangent))
        widened.append(target if level else half)
    return moved, widened


_Box = tuple[float, float, float, float]


def _boxes(
    built: list[tuple[list[tuple[Vec2, Vec2]], list[float]]],
    *,
    level: bool = False,
    envelope: Resolved | None = None,
) -> tuple[_Box, _Box]:
    """中心線と、太さを付けた外形の (xmin, xmax, ymin, ymax)。

    level では水平に走る所だけで測る。曲がり始めの膨らみはオーバーシュートとして残る。
    envelope を渡すと、外形はペンの包絡（`pen_envelope`）で測る。
    """
    if level:
        flat = []
        for samples, widths in built:
            kept = [
                (s, w)
                for s, w in zip(samples, widths)
                if abs(s[1].y) < abs(s[1].x) * 0.02
            ]
            if kept:
                flat.append(([s for s, _w in kept], [w for _s, w in kept]))
        built = flat or built
    xs: list[float] = []
    ys: list[float] = []
    oxs: list[float] = []
    oys: list[float] = []
    for samples, widths in built:
        if envelope is not None:
            xs.extend(pos.x for pos, _tangent in samples)
            ys.extend(pos.y for pos, _tangent in samples)
            for side in _envelope_sides(samples, widths, envelope):
                oxs.extend(point.x for point in side)
                oys.extend(point.y for point in side)
            continue
        for (pos, tangent), half in zip(samples, widths):
            xs.append(pos.x)
            ys.append(pos.y)
            length = tangent.length()
            if length < 1e-9:
                oxs.append(pos.x)
                oys.append(pos.y)
                continue
            normal = Vec2(-tangent.y / length, tangent.x / length)
            for side in (1.0, -1.0):
                edge = pos + normal * (half * side)
                oxs.append(edge.x)
                oys.append(edge.y)
    return (min(xs), max(xs), min(ys), max(ys)), (
        min(oxs),
        max(oxs),
        min(oys),
        max(oys),
    )


def _refit(
    off: float,
    scale: float,
    lo: float,
    hi: float,
    out_lo: float,
    out_hi: float,
    target: tuple[float, float],
):
    """外形が target に収まるよう、中心線の一次写像を直す。"""
    u_lo = (lo - off) / scale
    u_hi = (hi - off) / scale
    if abs(u_hi - u_lo) < 1e-9:
        return off, scale
    want_lo = target[0] + (lo - out_lo)
    want_hi = target[1] - (out_hi - hi)
    new_scale = (want_hi - want_lo) / (u_hi - u_lo)
    return want_lo - u_lo * new_scale, new_scale


def _fit_bowls(resolved: Resolved) -> tuple[dict[str, _Frame], float]:
    """碗の外形を基準線とオーバーシュートの位置に合わせる。

    閉じた碗は外形の縦横比と左の墨の位置を、太さぶんはみ出していた頃（分離を凍結した計測）の値に保つ。
    戻り値の2つ目は、閉じた碗が細くなったぶん字幅から引く量。
    """
    cap = resolved.style.cap_height
    frames: dict[str, _Frame] = {}
    shrink = 0.0
    bowls = [stroke for stroke in resolved.skeleton.strokes if stroke.role == "bowl"]
    groups: list[list[Stroke]] = [[s for s in bowls if _bowl_joined(s, resolved)]]
    groups += [[s] for s in bowls if not _bowl_joined(s, resolved)]
    for group in groups:
        if not group:
            continue
        overshoot = _bowl_overshoot(group[0], resolved)
        hi = cap + overshoot
        lo = -overshoot
        for side in _foot_sides(group[0]):
            if side == "top":
                hi = cap
            else:
                lo = 0.0
        target_y = (lo, hi)
        frame = _plain_frame(group[0], resolved)
        closed = group[0].closed
        target_x = None
        # 断面から描く碗の外形は、一番細い幅だけ外へ出る。位置合わせもその幅で測る。
        contrast = resolved.pen.type == "nib" and _bowl_joined(group[0], resolved)
        drawn = _stroke_resolved(group[0], resolved)
        envelope = drawn if _hairline_crown(group[0], resolved) else None
        ys = [knot.y for stroke in group for knot in stroke.knots]
        if _bowl_joined(group[0], resolved) and min(ys) > 0.02:
            # 基線まで届かない接合碗は、届いた範囲を天地へ伸ばさない。
            # 縦は、天地いっぱいの碗と同じく半幅だけ内側に寄せる。
            probe, probe_w = _centerline(group[0], drawn, frame)
            top = max(range(len(probe)), key=lambda i: probe[i][0].y)
            half = probe_w[top]
            fitted = _Frame(frame.x_off, frame.x_scale, half, cap - 2.0 * half)
            for stroke in group:
                frames[stroke.id] = fitted
            continue
        if closed:
            # 縦横比と左の位置は、丸の補正の前の太さで決める（分離を凍結した計測）。
            _line, ink = _boxes([_centerline(s, resolved, frame) for s in group])
            ratio = (ink[1] - ink[0]) / (ink[3] - ink[2])
            target_x = (ink[0], ink[0] + ratio * (target_y[1] - target_y[0]))
            shrink = max(shrink, ink[1] - target_x[1])
        for _ in range(4):
            built = [_centerline(s, drawn, frame, hug=not contrast) for s in group]
            if contrast:
                built = [
                    (samples, [min(widths)] * len(widths)) for samples, widths in built
                ]
            line, ink = _boxes(
                built, level=_bowl_joined(group[0], resolved), envelope=envelope
            )
            y_off, y_scale = _refit(
                frame.y_off, frame.y_scale, line[2], line[3], ink[2], ink[3], target_y
            )
            x_off, x_scale = frame.x_off, frame.x_scale
            if target_x is not None:
                x_off, x_scale = _refit(
                    x_off, x_scale, line[0], line[1], ink[0], ink[1], target_x
                )
            frame = _Frame(x_off, x_scale, y_off, y_scale)
        narrowed = _narrow_upper_bowl(frame, group, resolved)
        for stroke in group:
            frames[stroke.id] = narrowed.get(stroke.id, frame)
    return frames, shrink


def _narrow_upper_bowl(
    frame: _Frame, group: list[Stroke], resolved: Resolved
) -> dict[str, _Frame]:
    """上の碗だけ、左端を軸に upper_bowl 倍へ縮める。下の碗と幹は動かさない。"""
    factor = resolved.style.metrics.get("upper_bowl")
    if factor is None or len(group) < 2:
        return {}
    upper = max(group, key=lambda stroke: sum(knot.y for knot in stroke.knots))
    anchor_u = min(knot.x for knot in upper.knots)
    anchor = frame.x_off + anchor_u * frame.x_scale
    return {
        upper.id: _Frame(
            anchor + factor * (frame.x_off - anchor),
            frame.x_scale * factor,
            frame.y_off,
            frame.y_scale,
        )
    }


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


def _clip_behind_vertical_partner(
    poly: list[Vec2],
    samples: list[tuple[Vec2, Vec2]],
    stroke: Stroke,
    resolved: Resolved,
) -> list[Vec2]:
    """股の画が、縦の相手の向こう側へ端を出さない。"""
    if len(samples) < 2 or len(poly) < 4:
        return poly
    by_id = {item.id: item for item in resolved.skeleton.strokes}
    ring = list(poly)
    if (ring[0] - ring[-1]).length() < 1e-6:
        ring = ring[:-1]
    changed = False
    cap = resolved.style.cap_height
    for join in resolved.skeleton.joins:
        if join.type != "crotch" or stroke.id not in (join.a, join.b):
            continue
        partner_id = join.b if join.a == stroke.id else join.a
        partner = by_id.get(partner_id)
        if partner is None:
            continue
        xs = [knot.x for knot in partner.knots]
        if max(xs) - min(xs) > 0.02:
            continue
        frame = _plain_frame(partner, resolved)
        center = frame((sum(xs) / len(xs), 0.5))[0]
        half = half_width(resolved.pen, partner.role, math.pi / 2.0) * cap
        mid = samples[len(samples) // 2][0]
        # 幹の向こう側へだけ出さない。手前は重ねて、股の切れ目を埋める。
        if mid.x >= center:
            ring = _clip_vertical(ring, center - half, keep_left=False)
        else:
            ring = _clip_vertical(ring, center + half, keep_left=True)
        changed = True
    if not changed:
        return poly
    return _drop_close(ring)


def _bury(
    samples: dict[str, list[tuple[Vec2, Vec2]]],
    widths: dict[str, list[float]],
    joiner: str,
    partner: str,
) -> None:
    cur_s, cur_w = samples[joiner], widths[joiner]
    for at_start in (True, False):
        cur_s, cur_w = retract_end(
            cur_s, cur_w, samples[partner], widths[partner], at_start=at_start
        )
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
        if _hairline_crown(stroke, resolved):
            outer = box_ellipse(_envelope_outer(samples, widths, resolved))
            inner = box_ellipse(inner)
        outer_path = _to_path(outer)
        inner_path = _to_path(inner)
        if count_contours(inner_path):
            paths.append(_difference(outer_path, inner_path))
        else:
            paths.append(outer_path)
    else:
        diagonal = _diagonal_ends(samples, widths, stroke, resolved)
        ext_samples, ext_widths = list(samples), list(widths)
        boxes: list[list[Vec2]] = []
        serifs: list[list[Vec2]] = []
        for index, kind, origin, unit, half in diagonal:
            reach = half * abs(unit.x) / abs(unit.y) + 2.0
            tip = origin + unit * reach
            if index == 0:
                ext_samples.insert(0, (tip, samples[0][1]))
                ext_widths.insert(0, half)
            else:
                ext_samples.append((tip, samples[-1][1]))
                ext_widths.append(half)
            boxes.append(_beyond_box(origin, tip, unit, half))
            serifs.extend(_level_serif(origin, unit, half, kind, resolved))
        banded = _band_foot_cuts(samples, widths, stroke, resolved)
        if banded is not None:
            poly = banded
        else:
            poly = variable_width_outline(ext_samples, ext_widths, close=True)
            poly = _square_lateral_cuts(poly, samples, widths, stroke, resolved)
        poly = _clip_behind_vertical_partner(poly, samples, stroke, resolved)
        path = _to_path(poly)
        for box in boxes:
            path = _difference(path, _to_path(box))
        paths.append(path)
        paths.extend(_to_path(poly) for poly in serifs)
        skip = {index for index, *_rest in diagonal}
        paths.extend(_terminal_paths(samples, widths, stroke, resolved, skip=skip))
        return paths
    paths.extend(_terminal_paths(samples, widths, stroke, resolved))
    return paths


def _metric(resolved: Resolved, key: str) -> float:
    if key not in resolved.style.metrics:
        raise ValueError(f"{resolved.skeleton.glyph}: metrics.{key} required")
    return float(resolved.style.metrics[key])


def apex_meeting_y(a: Stroke, b: Stroke) -> float:
    """二つの画が最も近い端で会う高さ。節点空間。"""
    pairs = (
        (a.knots[0], b.knots[0]),
        (a.knots[0], b.knots[-1]),
        (a.knots[-1], b.knots[0]),
        (a.knots[-1], b.knots[-1]),
    )
    left, right = min(
        pairs,
        key=lambda pair: abs(pair[0].x - pair[1].x) + abs(pair[0].y - pair[1].y),
    )
    return (left.y + right.y) / 2.0


def _apex_joins(resolved: Resolved) -> list:
    """下向きの頂点だけ描く。天で会う尖りは帯の判定に使い、ここでは足さない。"""
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    return [
        join
        for join in resolved.skeleton.joins
        if join.type in ("apex", "apex_cut")
        and apex_meeting_y(by_id[join.a], by_id[join.b]) < 0.5
    ]


def _apex_join(resolved: Resolved):
    found = _apex_joins(resolved)
    return found[0] if found else None


def _at_y(start: Vec2, end: Vec2, y: float) -> Vec2:
    if abs(end.y - start.y) < 1e-9:
        return Vec2(end.x, y)
    t = (y - start.y) / (end.y - start.y)
    return start + (end - start) * t


def _quad(a: Vec2, control: Vec2, b: Vec2, steps: int = 8) -> list[Vec2]:
    points: list[Vec2] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        points.append(a * (u * u) + control * (2.0 * u * t) + b * (t * t))
    return points


def _leg_width(stroke: Stroke, resolved: Resolved, direction: Vec2) -> float:
    angle = math.atan2(direction.y, direction.x)
    slant = None
    if stroke.role == "slant_thin":
        slant = _metric(resolved, "slant_thin")
    return half_width(resolved.pen, stroke.role, angle, slant_ratio=slant) * resolved.style.cap_height * 2.0


def _outward(direction: Vec2, toward: float) -> Vec2:
    normal = direction.perpendicular().normalized()
    if normal.x * toward > 0.0:
        normal = -normal
    return normal


def _apex_paths(resolved: Resolved, join) -> list[Path]:
    """頂点は外縁と切り口で決める。脚の縁は直線で、太さは脚全体で一次に変わる。"""
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    left = by_id[join.a]
    right = by_id[join.b]
    frame = _plain_frame(left, resolved)
    cap = resolved.style.cap_height
    tip_y = -resolved.style.overshoot["apex"] * cap
    stem = resolved.style.pen.stem * cap
    taper = _metric(resolved, "apex_taper")

    def foot_of(stroke: Stroke) -> Vec2:
        knot = stroke.knots[0] if stroke.ends[0] != "apex" else stroke.knots[-1]
        x, y = frame((knot.x, knot.y))
        return Vec2(x, y)

    def apex_x(stroke: Stroke) -> float:
        knot = stroke.knots[-1] if stroke.ends[1] == "apex" else stroke.knots[0]
        return frame((knot.x, knot.y))[0]

    axis = (apex_x(left) + apex_x(right)) / 2.0
    kind = resolved.style.terminals["apex"]
    if kind == "round":
        radius = _metric(resolved, "apex_round") * stem
        return _round_apex(resolved, left, right, foot_of, axis, tip_y, radius, taper, cap)
    flat = _metric(resolved, "apex_flat") * stem
    ends = (Vec2(axis - flat / 2.0, tip_y), Vec2(axis + flat / 2.0, tip_y))
    legs = [
        _straight_leg(left, resolved, foot_of(left), ends[0], -1.0, taper, cap),
        _straight_leg(right, resolved, foot_of(right), ends[1], 1.0, taper, cap),
    ]
    covered = []
    for leg, far in ((legs[0], ends[1]), (legs[1], ends[0])):
        top, tip, inner, inner_top = leg.quad
        covered.append(_to_path([top, tip, far, inner, inner_top]))
    ink = _intersect(_union_all(covered), _to_path(_flat_envelope(legs, cap)))
    return [ink, *(_serif_paths(leg, resolved, cap) for leg in legs)]


def _upright_apex_joins(resolved: Resolved) -> list:
    """天で会う apex のうち、脚が地の頂点に使われていないもの。

    地の頂点の脚に載る天（W の中央）は、できた平らな天を持ち上げる側に残す。
    """
    taken = {join.a for join in _apex_joins(resolved)} | {
        join.b for join in _apex_joins(resolved)
    }
    return [
        join
        for join in _top_apex_joins(resolved)
        if join.a not in taken and join.b not in taken
    ]


def _up_apex_paths(resolved: Resolved, join) -> list[Path]:
    """天の頂点。V の外縁・平切り・一様な先細りを、足が基線になる向きにする。"""
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    left = by_id[join.a]
    right = by_id[join.b]
    frame = _plain_frame(left, resolved)
    cap = resolved.style.cap_height
    tip_y = cap + resolved.style.overshoot["apex"] * cap
    stem = resolved.style.pen.stem * cap
    taper = _metric(resolved, "apex_taper")

    def foot_of(stroke: Stroke) -> Vec2:
        knot = stroke.knots[0] if stroke.ends[0] != "apex" else stroke.knots[-1]
        x, y = frame((knot.x, knot.y))
        return Vec2(x, y)

    def apex_x(stroke: Stroke) -> float:
        knot = stroke.knots[-1] if stroke.ends[1] == "apex" else stroke.knots[0]
        return frame((knot.x, knot.y))[0]

    axis = (apex_x(left) + apex_x(right)) / 2.0
    if resolved.style.terminals["apex"] == "round":
        raise ValueError(f"{resolved.skeleton.glyph}: upward round apex is not built")
    flat = _metric(resolved, "apex_flat") * stem
    ends = (Vec2(axis - flat / 2.0, tip_y), Vec2(axis + flat / 2.0, tip_y))
    legs = [
        _straight_leg(left, resolved, foot_of(left), ends[0], -1.0, taper, 0.0),
        _straight_leg(right, resolved, foot_of(right), ends[1], 1.0, taper, 0.0),
    ]
    covered = []
    for leg, far in ((legs[0], ends[1]), (legs[1], ends[0])):
        top, tip, inner, inner_top = leg.quad
        covered.append(_to_path([top, tip, far, inner, inner_top]))
    ink = _intersect(_union_all(covered), _to_path(_flat_envelope(legs, 0.0)))
    return [ink]


@dataclass(frozen=True)
class _Leg:
    stroke: Stroke
    quad: list[Vec2]
    outer_top: Vec2
    inner_top: Vec2
    outer_line: tuple[Vec2, Vec2]
    width: float
    outward: float


def _straight_leg(
    stroke: Stroke,
    resolved: Resolved,
    foot: Vec2,
    outer_tip: Vec2,
    outward_x: float,
    taper: float,
    cut_y: float,
) -> _Leg:
    direction = (outer_tip - foot).normalized()
    width = _leg_width(stroke, resolved, direction)
    outward = _outward(direction, -outward_x)
    outer_foot = foot + outward * (width / 2.0)
    outer_line = (outer_foot, outer_tip)
    inward = -_outward(outer_tip - outer_foot, -outward_x)
    inner_foot = outer_foot + inward * width
    inner_tip = outer_tip + inward * (width * taper)
    outer_top = _at_y(outer_foot, outer_tip, cut_y)
    inner_top = _at_y(inner_foot, inner_tip, cut_y)
    quad = [outer_top, outer_tip, inner_tip, inner_top]
    return _Leg(stroke, quad, outer_top, inner_top, outer_line, width, outward_x)


def _flat_envelope(legs: list[_Leg], foot_y: float) -> list[Vec2]:
    left, right = legs
    return [left.outer_top, left.quad[1], right.quad[1], right.outer_top, Vec2(right.outer_top.x, foot_y), Vec2(left.outer_top.x, foot_y)]


def _intersect(outer: Path, inner: Path) -> Path:
    return op(outer, inner, PathOp.INTERSECTION)


def _round_apex(
    resolved: Resolved,
    left: Stroke,
    right: Stroke,
    foot_of,
    axis: float,
    tip_y: float,
    radius: float,
    taper: float,
    cap: float,
) -> list[Path]:
    """外縁は足の円と先端の円に接する直線。いちばん低い点は先端の円の底。"""
    tip = Vec2(axis, tip_y + radius)
    paths = [_to_path(_disk(tip, radius, -math.pi / 2.0))]
    legs = []
    for stroke, sign in ((left, -1.0), (right, 1.0)):
        foot = foot_of(stroke)
        direction = (Vec2(axis, tip_y) - foot).normalized()
        width = _leg_width(stroke, resolved, direction)
        center = Vec2(foot.x, cap - width / 2.0)
        paths.append(_to_path(_disk(center, width / 2.0, math.pi / 2.0)))
        legs.append(_round_leg(center, width, tip, radius, sign, taper))
    crotch = _line_hit(legs[0][3], legs[0][4], legs[1][3], legs[1][4])
    for center, outer_foot, outer_tip, inner_foot, _target in legs:
        paths.append(_to_path([outer_foot, outer_tip, tip, crotch, inner_foot, center]))
    return paths


def _disk(center: Vec2, radius: float, lock_angle: float) -> list[Vec2]:
    steps = 64
    return [
        Vec2(
            center.x + radius * math.cos(lock_angle + 2.0 * math.pi * i / steps),
            center.y + radius * math.sin(lock_angle + 2.0 * math.pi * i / steps),
        )
        for i in range(steps)
    ]


def _external_tangents(start: Vec2, start_r: float, end: Vec2, end_r: float) -> list[tuple[Vec2, Vec2]]:
    delta = end - start
    dist = delta.length()
    if dist <= abs(start_r - end_r) + 1.0:
        raise ValueError("apex round overlaps the foot")
    vx, vy = delta.x / dist, delta.y / dist
    ratio = (start_r - end_r) / dist
    span = math.sqrt(max(0.0, 1.0 - ratio * ratio))
    found = []
    for sign in (-1.0, 1.0):
        nx = vx * ratio - sign * span * vy
        ny = vy * ratio + sign * span * vx
        found.append(
            (
                Vec2(start.x + start_r * nx, start.y + start_r * ny),
                Vec2(end.x + end_r * nx, end.y + end_r * ny),
            )
        )
    return found


def _round_leg(
    foot: Vec2,
    width: float,
    tip: Vec2,
    tip_r: float,
    sign: float,
    taper: float,
) -> tuple[Vec2, Vec2, Vec2, Vec2, Vec2]:
    radius = width / 2.0
    tangents = _external_tangents(foot, radius, tip, tip_r)
    outer = max(tangents, key=lambda seg: (seg[0].x - foot.x) * sign)
    inward = -_outward(outer[1] - outer[0], -sign)
    target = outer[1] + inward * (width * taper)
    inner = _tangent_from(foot, radius, target, sign)
    return foot, outer[0], outer[1], inner, target


def _line_hit(a0: Vec2, a1: Vec2, b0: Vec2, b1: Vec2) -> Vec2:
    da, db = a1 - a0, b1 - b0
    det = da.cross(db)
    if abs(det) < 1e-9:
        return (a1 + b1) * 0.5
    t = (b0 - a0).cross(db) / det
    return a0 + da * t


def _tangent_from(center: Vec2, radius: float, target: Vec2, sign: float) -> Vec2:
    delta = target - center
    dist2 = delta.dot(delta)
    disc = dist2 - radius * radius
    if disc <= 1.0:
        return center + delta.normalized() * radius
    root = math.sqrt(disc)
    scale = radius / dist2
    points = (
        Vec2(
            center.x + scale * (radius * delta.x + root * delta.y),
            center.y + scale * (radius * delta.y - root * delta.x),
        ),
        Vec2(
            center.x + scale * (radius * delta.x - root * delta.y),
            center.y + scale * (radius * delta.y + root * delta.x),
        ),
    )
    return max(points, key=lambda point: (point.x - center.x) * -sign)


def _serif_paths(leg: _Leg, resolved: Resolved, cap: float) -> Path:
    stroke = leg.stroke
    tag = stroke.ends[0] if stroke.ends[0] != "apex" else stroke.ends[1]
    kind = resolved.style.terminals[tag]
    if kind not in _SERIF_KINDS:
        return Path()
    thick = max(resolved.style.metrics.get("serif_thick", 0.02) * cap, 1.0)
    length = resolved.style.metrics.get("serif_length", 0.12) * cap
    if kind == "spur":
        length *= 0.45
    underside = cap - thick
    outer_edge = leg.outer_line
    inner_edge = (leg.quad[3], leg.quad[2])
    outer_xs = (_at_y(*outer_edge, cap).x, _at_y(*outer_edge, underside).x)
    inner_xs = (_at_y(*inner_edge, cap).x, _at_y(*inner_edge, underside).x)
    if leg.outward < 0.0:
        outer_x, inner_x = min(outer_xs), max(inner_xs)
    else:
        outer_x, inner_x = max(outer_xs), min(inner_xs)
    extra = max(length - abs(inner_x - outer_x), thick * 2.0)
    outer_extra = extra * 0.62
    inner_extra = extra - outer_extra
    if leg.outward < 0.0:
        lo = outer_x - outer_extra
        hi = inner_x + inner_extra
    else:
        lo = inner_x - inner_extra
        hi = outer_x + outer_extra
    slab = [Vec2(lo, cap), Vec2(hi, cap), Vec2(hi, cap - thick), Vec2(lo, cap - thick)]
    paths = [_to_path(slab)]
    if kind == "serif_bracketed":
        reach = resolved.style.metrics.get("bracket", 0.0) * cap
        if reach > 1.0:
            for edge in (leg.outer_line, (leg.quad[3], leg.quad[2])):
                paths.append(_to_path(_bracket_fillet(edge, cap - thick, reach, lo, hi)))
    return _union_all(paths)


def _bracket_fillet(
    edge: tuple[Vec2, Vec2],
    underside: float,
    reach: float,
    lo: float,
    hi: float,
    *,
    toward: float = -1.0,
) -> list[Vec2]:
    """下面と脚の縁を、両端で接線がつながる凹の曲線でつなぐ。toward は曲線が板から離れる y の向き。"""
    start, end = edge
    if abs(end.y - start.y) < 1e-6:
        return [start, end]
    corner = _at_y(start, end, underside)
    direction = (end - start).normalized()
    if direction.y * toward < 0.0:
        direction = -direction
    along = corner + direction * reach
    outward = -1.0 if corner.x <= (lo + hi) / 2.0 else 1.0
    side = Vec2(max(lo, min(hi, corner.x + outward * reach)), underside)
    curve = _quad(side, corner, along, 48)
    return [*curve, corner]


_CUT_KINDS = ("flat", "apex_sharp", "apex_cut")
_SERIF_KINDS = ("serif_bracketed", "serif_hairline", "spur")


def _square_lateral_cuts(
    poly: list[Vec2],
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> list[Vec2]:
    """横を向いた碗の平切りは、切り口を垂直にする。

    接線に直角の切り口は斜めの直線になり、軸に乗らない。
    """
    if resolved.skeleton.structure != "bowl" or len(samples) < 2 or len(poly) < 4:
        return poly
    cuts: list[tuple[float, bool]] = []
    last = len(samples) - 1
    for index, sign, tag in ((0, -1.0, stroke.ends[0]), (last, 1.0, stroke.ends[1])):
        if tag != "open" or resolved.style.terminals.get(tag) != "flat":
            continue
        origin, tangent = samples[index]
        unit = tangent * sign
        if unit.length() < 1e-9:
            continue
        outward = unit.normalized()
        if abs(outward.x) < 0.2:
            continue
        normal = tangent.perpendicular().normalized()
        half = widths[index]
        ends = ((origin + normal * half).x, (origin - normal * half).x)
        if outward.x > 0.0:
            cuts.append((min(ends), True))
        else:
            cuts.append((max(ends), False))
    if not cuts:
        return poly
    ring = list(poly)
    if (ring[0] - ring[-1]).length() < 1e-6:
        ring = ring[:-1]
    for cut_x, keep_left in cuts:
        ring = _clip_vertical(ring, cut_x, keep_left=keep_left)
    return _drop_close(ring)


def _band_foot_cuts(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> list[Vec2] | None:
    """斜めの足は、端を延ばしてから端の y で水平に切る。

    延ばさないと、切り口が画の片側にしか当たらない。箱で切ると角が残る。
    """
    if len(samples) < 2:
        return None
    cuts: list[tuple[int, float, Vec2]] = []
    last = len(samples) - 1
    for index, sign, tag in ((0, -1.0, stroke.ends[0]), (last, 1.0, stroke.ends[1])):
        if tag != "foot" or resolved.style.terminals.get(tag) != "flat":
            continue
        origin, tangent = samples[index]
        unit = tangent * sign
        if unit.length() < 1e-9:
            continue
        outward = unit.normalized()
        if abs(outward.y) < 0.5 or abs(outward.x) < 0.05:
            continue
        cuts.append((index, origin.y, outward))
    if not cuts:
        return None
    extended = list(samples)
    extended_w = list(widths)
    for index, _cut_y, outward in sorted(cuts, reverse=True):
        half = widths[index]
        reach = half * abs(outward.x) / abs(outward.y) + 2.0
        tip = (samples[index][0] + outward * reach, samples[index][1])
        if index == 0:
            extended.insert(0, tip)
            extended_w.insert(0, half)
        else:
            extended.append(tip)
            extended_w.append(half)
    poly = variable_width_outline(extended, extended_w, close=True)
    ring = list(poly)
    if ring and (ring[0] - ring[-1]).length() < 1e-6:
        ring = ring[:-1]
    for _index, cut_y, outward in cuts:
        ring = _clip_horizontal(ring, cut_y, keep_below=outward.y > 0.0)
    ring = _drop_close(ring)
    # 碗に付く脚だけ。延ばした端のサンプルが、切ったあとの直線上に残る。
    if any(
        item.role == "bowl" for item in resolved.skeleton.strokes
    ) and _has_diagonal_foot(resolved):
        ring = _drop_colinear(ring)
    return ring


def _clip_horizontal(poly: list[Vec2], cut_y: float, *, keep_below: bool) -> list[Vec2]:
    def inside(point: Vec2) -> bool:
        if keep_below:
            return point.y <= cut_y + 1e-6
        return point.y >= cut_y - 1e-6

    def hit(start: Vec2, end: Vec2) -> Vec2:
        dy = end.y - start.y
        t = 0.0 if abs(dy) < 1e-9 else (cut_y - start.y) / dy
        t = max(0.0, min(1.0, t))
        return Vec2(start.x + (end.x - start.x) * t, cut_y)

    output: list[Vec2] = []
    for index, cur in enumerate(poly):
        prev = poly[index - 1]
        prev_in, cur_in = inside(prev), inside(cur)
        if cur_in:
            if not prev_in:
                output.append(hit(prev, cur))
            output.append(cur)
        elif prev_in:
            output.append(hit(prev, cur))
    return output


def _clip_vertical(poly: list[Vec2], cut_x: float, *, keep_left: bool) -> list[Vec2]:
    def inside(point: Vec2) -> bool:
        if keep_left:
            return point.x <= cut_x + 1e-6
        return point.x >= cut_x - 1e-6

    def hit(start: Vec2, end: Vec2) -> Vec2:
        dx = end.x - start.x
        t = 0.0 if abs(dx) < 1e-9 else (cut_x - start.x) / dx
        t = max(0.0, min(1.0, t))
        return Vec2(cut_x, start.y + (end.y - start.y) * t)

    output: list[Vec2] = []
    for index, cur in enumerate(poly):
        prev = poly[index - 1]
        prev_in, cur_in = inside(prev), inside(cur)
        if cur_in:
            if not prev_in:
                output.append(hit(prev, cur))
            output.append(cur)
        elif prev_in:
            output.append(hit(prev, cur))
    return output


def _drop_colinear(poly: list[Vec2], limit: float = 1.0) -> list[Vec2]:
    """曲がりが limit 度未満の点を落とす。直線の上のサンプルを節にしない。"""
    if len(poly) < 4:
        return poly
    kept: list[Vec2] = []
    count = len(poly)
    for index, point in enumerate(poly):
        prev, nxt = poly[index - 1], poly[(index + 1) % count]
        v1x, v1y = point.x - prev.x, point.y - prev.y
        v2x, v2y = nxt.x - point.x, nxt.y - point.y
        if math.hypot(v1x, v1y) < 1e-9 or math.hypot(v2x, v2y) < 1e-9:
            continue
        turn = abs(math.degrees(math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y)))
        if turn < limit:
            continue
        kept.append(point)
    return kept or poly


def _drop_close(poly: list[Vec2], gap: float = 0.4) -> list[Vec2]:
    if not poly:
        return poly
    kept = [poly[0]]
    for point in poly[1:]:
        if (point - kept[-1]).length() > gap:
            kept.append(point)
    if len(kept) > 2 and (kept[0] - kept[-1]).length() <= gap:
        kept = kept[:-1]
    return kept


def _diagonal_ends(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> list[tuple[int, str, Vec2, Vec2, float]]:
    """斜めの画と背骨の端は、切り口を水平にそろえる。

    碗の平切りは弧の端のままにする。水平に切り直すと、切り口の前に段ができる。
    """
    found: list[tuple[int, str, Vec2, Vec2, float]] = []
    last = len(samples) - 1
    for index, sign, tag in ((0, -1.0, stroke.ends[0]), (last, 1.0, stroke.ends[1])):
        kind = resolved.style.terminals[tag]
        if kind not in _CUT_KINDS + _SERIF_KINDS:
            continue
        if resolved.skeleton.structure == "bowl" and kind == "flat":
            continue
        origin, tangent = samples[index]
        unit = (tangent * sign).normalized()
        if abs(unit.y) < 0.5 or abs(unit.x) < 0.05:
            continue
        found.append((index, kind, origin, unit, widths[index]))
    return found


def _beyond_box(origin: Vec2, tip: Vec2, unit: Vec2, half: float) -> list[Vec2]:
    """端の水平線より外に出た部分だけを覆う箱。"""
    depth = (tip - origin).length() * abs(unit.y) + half * abs(unit.x) + 4.0
    lo = min(origin.x, tip.x) - half - 4.0
    hi = max(origin.x, tip.x) + half + 4.0
    if unit.y > 0.0:
        y0, y1 = origin.y, origin.y + depth
    else:
        y0, y1 = origin.y - depth, origin.y
    return [Vec2(lo, y0), Vec2(hi, y0), Vec2(hi, y1), Vec2(lo, y1)]


def _level_serif(
    origin: Vec2, unit: Vec2, half: float, kind: str, resolved: Resolved
) -> list[list[Vec2]]:
    """斜めの画に載せる水平なセリフ。張り出しは幹のセリフと同じ量にする。"""
    if kind not in _SERIF_KINDS:
        return []
    style = resolved.style
    cap = style.cap_height
    thick = max(style.metrics.get("serif_thick", 0.02) * cap, 1.0)
    length = style.metrics.get("serif_length", 0.12) * cap
    if kind == "spur":
        length *= 0.45
    stem_full = resolved.pen.stem * cap
    overhang = max((length - stem_full) / 2.0, thick)
    sign = 1.0 if unit.y > 0.0 else -1.0
    run = unit.x / unit.y
    cross = half / abs(unit.y)

    def center(y: float) -> float:
        return origin.x + (y - origin.y) * run

    face = origin.y
    back = origin.y - sign * thick * 1.35
    span = cross + overhang
    # 切り口と同じ水平の板で、両端は垂直。長さは画の厚みの中ほどで測る。
    middle = center((face + back) / 2.0)
    lo, hi = middle - span, middle + span
    polys = [[Vec2(lo, face), Vec2(hi, face), Vec2(hi, back), Vec2(lo, back)]]
    if kind == "serif_bracketed":
        reach = max(style.metrics.get("bracket", 0.0) * cap, thick)
        beyond = back - sign * reach
        for offset in (-cross, cross):
            edge = (Vec2(center(back) + offset, back), Vec2(center(beyond) + offset, beyond))
            polys.append(_bracket_fillet(edge, back, reach, lo, hi, toward=-sign))
    return polys


def _bowl_edge(pos: Vec2, tangent: Vec2, half: float, *, low: bool) -> float:
    unit = tangent.normalized() if tangent.length() > 1e-9 else Vec2(0.0, 1.0)
    drop = abs(unit.x) * half
    return pos.y - drop if low else pos.y + drop


def _extend_bowl_stems(
    samples: dict[str, list[tuple[Vec2, Vec2]]],
    widths: dict[str, list[float]],
    resolved: Resolved,
) -> None:
    """碗が幹の端より外にはみ出す分だけ、幹を延ばす。セリフはその先に付く。"""
    by_stem: dict[str, list[str]] = {}
    for join in resolved.skeleton.joins:
        if join.type == "bowl_join" and join.b in samples and join.a in samples:
            by_stem.setdefault(join.b, []).append(join.a)
    for stroke in resolved.skeleton.strokes:
        partners = by_stem.get(stroke.id)
        if not partners:
            continue
        pts = samples[stroke.id]
        ws = widths[stroke.id]
        if len(pts) < 2:
            continue
        for at_start, tag in ((True, stroke.ends[0]), (False, stroke.ends[1])):
            kind = resolved.style.terminals[tag]
            # 平切りの幹は基準線で止める。丸い碗が先へ出ても、幹は追わない。
            if kind not in (
                "round",
                "serif_bracketed",
                "serif_hairline",
                "spur",
            ):
                continue
            index = 0 if at_start else -1
            origin, tangent = pts[index]
            outward = tangent * (-1.0 if at_start else 1.0)
            if outward.length() < 1e-9:
                continue
            unit = outward.normalized()
            low = unit.y < 0.0
            window = max(ws[index] * 2.2, 40.0)
            extreme: float | None = None
            strokes_by_id = {item.id: item for item in resolved.skeleton.strokes}
            for bowl_id in partners:
                bowl_widths = widths[bowl_id]
                # 断面の碗の外形は一番細い幅だけ外へ出る。幹もそこまでで止める。
                outer_half = (
                    min(bowl_widths)
                    if _nib_bowl(strokes_by_id[bowl_id], resolved)
                    else None
                )
                for (pos, tang), half in zip(samples[bowl_id], bowl_widths):
                    if abs(pos.x - origin.x) > window:
                        continue
                    edge = _bowl_edge(
                        pos,
                        tang,
                        outer_half if outer_half is not None else half,
                        low=low,
                    )
                    if extreme is None or (edge < extreme if low else edge > extreme):
                        extreme = edge
            if extreme is None:
                continue
            face = _round_radius(kind, ws[index], resolved)
            target_y = extreme - unit.y * face
            reach = (
                (target_y - origin.y) / unit.y
                if abs(unit.y) > 0.5
                else (Vec2(0.0, target_y) - origin).dot(unit)
            )
            if reach < 1.0:
                continue
            moved = origin + unit * reach
            if at_start:
                pts.insert(0, (moved, tangent))
                ws.insert(0, ws[0])
            else:
                pts.append((moved, tangent))
                ws.append(ws[-1])


def _nib_bowl(stroke: Stroke, resolved: Resolved) -> bool:
    return (
        resolved.pen.type == "nib"
        and stroke.role == "bowl"
        and _bowl_joined(stroke, resolved)
    )


def _hairline_crown(stroke: Stroke, resolved: Resolved) -> bool:
    """細い方向が水平な、接合のない閉じた碗。天地で穴がレンズになる（シックの O と 0）。"""
    return (
        resolved.pen.type == "nib"
        and resolved.pen.theta_deg == 0.0
        and stroke.closed
        and stroke.role == "bowl"
        and not _bowl_joined(stroke, resolved)
    )


def _envelope_sides(
    samples: list[tuple[Vec2, Vec2]], widths: list[float], resolved: Resolved
) -> tuple[list[Vec2], list[Vec2]]:
    cap = resolved.style.cap_height
    pen = resolved.pen
    return pen_envelope(
        samples,
        widths,
        stem=pen.stem * cap,
        hairline=pen.hairline * cap,
        theta_deg=pen.theta_deg,
    )


def _envelope_outer(
    samples: list[tuple[Vec2, Vec2]], widths: list[float], resolved: Resolved
) -> list[Vec2]:
    work, halves = list(samples), list(widths)
    if len(work) >= 2 and (work[0][0] - work[-1][0]).length() < 1e-6:
        work, halves = work[:-1], halves[:-1]
    left, right = _envelope_sides(work, halves, resolved)
    return max(left, right, key=lambda ring: abs(_signed_area(ring)))


def _open_nib_arm(resolved: Resolved) -> bool:
    """接合のない開いた碗。クラシックとシックの S がこれで、閉じた O や B は違う。"""
    strokes = resolved.skeleton.strokes
    if resolved.pen.type != "nib" or len(strokes) != 1 or resolved.skeleton.joins:
        return False
    stroke = strokes[0]
    return not stroke.closed and stroke.role == "bowl" and "open" in stroke.ends


def _facing_start(stroke: Stroke, resolved: Resolved) -> bool:
    """この端が、もう一方の碗と向かい合う横棒側か。"""
    others = [
        other
        for other in resolved.skeleton.strokes
        if other.role == "bowl" and other.id != stroke.id
    ]
    if not others:
        return True
    mid = (others[0].knots[0].y + others[0].knots[-1].y) / 2.0
    return abs(stroke.knots[0].y - mid) <= abs(stroke.knots[-1].y - mid)


def _contrast_path(
    stroke: Stroke, resolved: Resolved, frame: _Frame, samples, widths
) -> Path:
    """ペンでなぞらず、外形と穴を断面から描く。端は幹の中心線まで戻す。"""
    raw_s, raw_w = _centerline(stroke, resolved, frame, hug=False)
    partner = next(
        join.b
        for join in resolved.skeleton.joins
        if join.type == "bowl_join" and join.a == stroke.id
    )
    for at_start in (True, False):
        raw_s, raw_w = retract_end(
            raw_s, raw_w, samples[partner], widths[partner], at_start=at_start
        )
    polygon = contrast_polygon(
        raw_s,
        raw_w,
        bar_half=_serif_bar_half(resolved),
        theta_deg=resolved.pen.theta_deg,
        facing_start=_facing_start(stroke, resolved),
    )
    return _to_path(polygon)


def _seat_arms(resolved: Resolved) -> Resolved:
    """y が 0 または 1 の腕は、外縁をその基準線に合わせ、中心を半幅だけ内側へ置く。"""
    strokes = []
    changed = False
    for stroke in resolved.skeleton.strokes:
        if stroke.role != "arm":
            strokes.append(stroke)
            continue
        ys = [knot.y for knot in stroke.knots]
        if max(ys) - min(ys) > 1e-6:
            strokes.append(stroke)
            continue
        half = half_width(resolved.pen, stroke.role, 0.0)
        if ys[0] >= 1.0 - 1e-6:
            seated = 1.0 - half
        elif ys[0] <= 1e-6:
            seated = half
        else:
            strokes.append(stroke)
            continue
        knots = tuple(replace(knot, y=seated) for knot in stroke.knots)
        strokes.append(replace(stroke, knots=knots))
        changed = True
    if not changed:
        return resolved
    return replace(
        resolved, skeleton=replace(resolved.skeleton, strokes=tuple(strokes))
    )


def _raise_bars(resolved: Resolved) -> Resolved:
    """横棒の中心は骨格の y ではなく、様式の metrics.bar_y。"""
    strokes = []
    changed = False
    for stroke in resolved.skeleton.strokes:
        if stroke.role != "bar":
            strokes.append(stroke)
            continue
        if "bar_y" not in resolved.style.metrics:
            raise ValueError(f"{resolved.skeleton.glyph}: metrics.bar_y required")
        y = float(resolved.style.metrics["bar_y"])
        knots = tuple(replace(knot, y=y) for knot in stroke.knots)
        strokes.append(replace(stroke, knots=knots))
        changed = True
    if not changed:
        return resolved
    return replace(resolved, skeleton=replace(resolved.skeleton, strokes=tuple(strokes)))


def _has_diagonal_foot(resolved: Resolved) -> bool:
    """足の節点が斜めに入る。頂点の切り口とは別の脚。"""
    for stroke in resolved.skeleton.strokes:
        knots = stroke.knots
        ends = ((0, stroke.ends[0]), (len(knots) - 1, stroke.ends[1]))
        for index, tag in ends:
            if tag != "foot" or len(knots) < 2:
                continue
            other = 1 if index == 0 else index - 1
            dx = knots[index].x - knots[other].x
            dy = knots[index].y - knots[other].y
            if abs(dx) > 0.05 and abs(dy) > 0.05:
                return True
    return False


def _flatten_shared_cap(contour: list[Vec2], cap: float) -> list[Vec2]:
    """頂点を二つ足した字の、天で隣り合う足の段を消す。

    輪郭演算が天の 0.5 UPM 以内に残す段を、キャップへ揃えて落とす。
    """
    closed = len(contour) > 1 and (contour[0] - contour[-1]).length() < 1e-6
    points = list(contour[:-1] if closed else contour)
    snapped = [
        Vec2(point.x, cap) if abs(point.y - cap) <= 0.5 else point for point in points
    ]
    if not snapped:
        return list(contour)
    kept = [snapped[0]]
    for point in snapped[1:]:
        if (point - kept[-1]).length() >= 0.5:
            kept.append(point)
    if len(kept) > 1 and (kept[0] - kept[-1]).length() < 0.5:
        kept.pop()
    if closed and kept:
        kept.append(kept[0])
    return kept


def _side_amount(style, name: str) -> float:
    return style.sidebearing["base"] * style.cap_height * style.sidebearing[name]


def _seat_on_ink(contours, holes, left: float):
    """墨の左端を側面の位置まで平行移動する。戻り値は移動後の輪郭と墨の幅。"""
    xs = [
        point.x
        for contour, hole in zip(contours, holes, strict=True)
        if not hole
        for point in contour
    ]
    x0, x1 = min(xs), max(xs)
    dx = left - x0
    moved = tuple(
        tuple(Vec2(point.x + dx, point.y) for point in contour) for contour in contours
    )
    return moved, x1 - x0


def _axis_x(stroke: Stroke, resolved: Resolved) -> float:
    frame = _plain_frame(stroke, resolved)
    return frame((stroke.knots[0].x, stroke.knots[0].y))[0]


def _on_line(origin: tuple[float, float], direction: tuple[float, float], x: float) -> float:
    return origin[1] + (x - origin[0]) / direction[0] * direction[1]


def _clean_ring(points: list[Vec2]) -> list[Vec2]:
    """辺の上に載った点を輪郭演算でほどき、単純な外周にする。"""
    cleaned = simplify(_to_path(points), fix_winding=True)
    rings: list[list[Vec2]] = []
    for contour in split_contours(cleaned):
        body = [Vec2(x, y) for x, y in contour_points(contour)]
        if len(body) > 1 and (body[0] - body[-1]).length() < 1e-4:
            body = body[:-1]
        if len(body) >= 3:
            rings.append(body)
    ring = max(rings, key=lambda item: abs(_signed_area(item)))
    # 同じ点を二度通ると、角の数よりオンカーブ点が増える。
    unique: list[Vec2] = []
    for point in ring:
        if any((point - kept).length() < 0.4 for kept in unique):
            continue
        unique.append(point)
    return unique


def _constant_gap_direction(
    start: tuple[float, float],
    end: tuple[float, float],
    gap: float,
    probe_x: float,
) -> tuple[float, float]:
    """start を通る直線と、end を通る平行線の距離が gap になる単位方向。

    probe_x では、start 側の線が end 側より上に来る向きを取る。
    """
    vx, vy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(vx, vy)
    if not 0.0 < gap < length:
        raise ValueError(f"diagonal gap {gap} does not fit length {length}")
    ux, uy = vx / length, vy / length
    alpha = math.asin(gap / length)
    for sign in (1.0, -1.0):
        cosine, sine = math.cos(sign * alpha), math.sin(sign * alpha)
        direction = (cosine * ux - sine * uy, sine * ux + cosine * uy)
        if _on_line(start, direction, probe_x) > _on_line(end, direction, probe_x):
            return direction
    raise ValueError("diagonal edges do not separate")


def _dir_hit(
    origin: tuple[float, float],
    direction: tuple[float, float],
    other: tuple[float, float],
    other_d: tuple[float, float],
) -> tuple[float, float]:
    det = direction[0] * other_d[1] - direction[1] * other_d[0]
    t = ((other[0] - origin[0]) * other_d[1] - (other[1] - origin[1]) * other_d[0]) / det
    return (origin[0] + direction[0] * t, origin[1] + direction[1] * t)


def _font_knot(stroke: Stroke, resolved: Resolved, knot: Knot) -> Vec2:
    x, y = _plain_frame(stroke, resolved)((knot.x, knot.y))
    return Vec2(x, y)


def _closest_knots(a: Stroke, b: Stroke) -> tuple[Knot, Knot]:
    pairs = (
        (a.knots[0], b.knots[0]),
        (a.knots[0], b.knots[-1]),
        (a.knots[-1], b.knots[0]),
        (a.knots[-1], b.knots[-1]),
    )
    return min(
        pairs,
        key=lambda pair: abs(pair[0].x - pair[1].x) + abs(pair[0].y - pair[1].y),
    )


def _far_knot(diagonal: Stroke, stem: Stroke) -> Knot:
    meeting, _stem_knot = _closest_knots(diagonal, stem)
    for knot in (diagonal.knots[0], diagonal.knots[-1]):
        if knot is not meeting:
            return knot
    return diagonal.knots[-1]


def _foot_band(stroke: Stroke, resolved: Resolved, high: bool) -> float | None:
    """足の端の高さ。尖り側は切り口なので None。"""
    first, last = stroke.knots[0], stroke.knots[-1]
    if high:
        knot = last if last.y >= first.y else first
    else:
        knot = first if first.y <= last.y else last
    tag = stroke.ends[0] if knot is first else stroke.ends[-1]
    if tag != "foot":
        return None
    return resolved.style.cap_height if knot.y >= 0.5 else 0.0


def _strip_width(stroke: Stroke, resolved: Resolved, full: float) -> float:
    """両端が頂点の斜画は crotch_thin 倍の一定幅。"""
    if stroke.ends[0] == "apex" and stroke.ends[1] == "apex":
        return resolved.style.joins["crotch_thin"] * full
    return full


@dataclass(frozen=True)
class _StemCorner:
    stem: Stroke
    diagonal: Stroke
    meeting_y: float
    outer: float
    inner: float
    inward: float
    flat_pt: tuple[float, float]
    top: bool


def _stem_corners(resolved: Resolved) -> list[_StemCorner]:
    style = resolved.style
    cap = style.cap_height
    full = resolved.pen.stem * cap
    flat = float(style.metrics["apex_flat"]) * full
    overshoot = style.overshoot["apex"] * cap
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    corners = []
    for join in resolved.skeleton.joins:
        if join.type != "stem_apex":
            continue
        stem, diagonal = by_id[join.a], by_id[join.b]
        stem_knot, diag_knot = _closest_knots(stem, diagonal)
        meeting_y = (stem_knot.y + diag_knot.y) / 2.0
        axis = _axis_x(stem, resolved)
        inward = 1.0 if _font_knot(diagonal, resolved, _far_knot(diagonal, stem)).x >= axis else -1.0
        outer = axis - inward * (full / 2.0)
        top = meeting_y >= 0.5
        y = cap + overshoot if top else -overshoot
        corners.append(
            _StemCorner(
                stem,
                diagonal,
                meeting_y,
                outer,
                outer + inward * full,
                inward,
                (outer + inward * flat, y),
                top,
            )
        )
    return corners


def _shared_apex_x(resolved: Resolved, diagonals: set[str]) -> float:
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    for join in resolved.skeleton.joins:
        if join.type not in ("apex", "apex_cut"):
            continue
        if {join.a, join.b} != diagonals:
            continue
        left, right = _closest_knots(by_id[join.a], by_id[join.b])
        return (
            _font_knot(by_id[join.a], resolved, left).x
            + _font_knot(by_id[join.b], resolved, right).x
        ) / 2.0
    raise ValueError(f"{resolved.skeleton.glyph}: diagonal apex join missing")


def _stem_apex_ring(resolved: Resolved) -> list[Vec2]:
    """幹と斜画の外頂点。斜画の節点と幹の節点から、一定幅の縁を引く。"""
    style = resolved.style
    cap = style.cap_height
    full = resolved.pen.stem * cap
    flat = float(style.metrics["apex_flat"]) * full
    overshoot = style.overshoot["apex"] * cap
    peak, tip = cap + overshoot, -overshoot
    corners = _stem_corners(resolved)
    by_diagonal: dict[str, list[_StemCorner]] = {}
    for corner in corners:
        by_diagonal.setdefault(corner.diagonal.id, []).append(corner)
    if len(by_diagonal) == 1 and len(corners) == 2:
        return _one_diagonal_ring(corners, resolved, full, peak, tip)
    if len(by_diagonal) == 2 and len(corners) == 2:
        return _two_diagonal_ring(corners, resolved, full, flat, peak, tip)
    raise ValueError(f"{resolved.skeleton.glyph}: unsupported stem_apex layout")


def _one_diagonal_ring(
    corners: list[_StemCorner],
    resolved: Resolved,
    full: float,
    peak: float,
    tip: float,
) -> list[Vec2]:
    """斜画1本が、天の頂点と地の頂点をつなぐ。"""
    top = next(corner for corner in corners if corner.top)
    bottom = next(corner for corner in corners if not corner.top)
    if top.outer > bottom.outer:
        raise ValueError(f"{resolved.skeleton.glyph}: top stem_apex is not on the left")
    weight = _strip_width(top.diagonal, resolved, full)
    direction = _constant_gap_direction(top.flat_pt, bottom.flat_pt, weight, top.inner)
    low = _foot_band(top.stem, resolved, high=False)
    high = _foot_band(bottom.stem, resolved, high=True)
    if low is None or high is None:
        raise ValueError(f"{resolved.skeleton.glyph}: stem foot missing")
    crotch_top = _on_line(bottom.flat_pt, direction, top.inner)
    crotch_bottom = _on_line(top.flat_pt, direction, bottom.inner)
    return _clean_ring(
        [
            Vec2(top.outer, low),
            Vec2(top.inner, low),
            Vec2(top.inner, crotch_top),
            Vec2(*bottom.flat_pt),
            Vec2(bottom.outer, tip),
            Vec2(bottom.outer, high),
            Vec2(bottom.inner, high),
            Vec2(bottom.inner, crotch_bottom),
            Vec2(*top.flat_pt),
            Vec2(top.outer, peak),
        ]
    )


def _two_diagonal_ring(
    corners: list[_StemCorner],
    resolved: Resolved,
    full: float,
    flat: float,
    peak: float,
    tip: float,
) -> list[Vec2]:
    """左右の天は幹との外頂点。谷は2本の斜画の下の頂点。"""
    left, right = sorted(corners, key=lambda corner: corner.outer)
    apex_x = _shared_apex_x(resolved, {left.diagonal.id, right.diagonal.id})
    left_tip = (apex_x - left.inward * flat / 2.0, tip)
    right_tip = (apex_x - right.inward * flat / 2.0, tip)
    left_dir = _constant_gap_direction(
        left.flat_pt, left_tip, _strip_width(left.diagonal, resolved, full), left.inner
    )
    right_dir = _constant_gap_direction(
        right.flat_pt, right_tip, _strip_width(right.diagonal, resolved, full), right.inner
    )
    left_low = _foot_band(left.stem, resolved, high=False)
    right_low = _foot_band(right.stem, resolved, high=False)
    if left_low is None or right_low is None:
        raise ValueError(f"{resolved.skeleton.glyph}: stem foot missing")
    crotch_l = _on_line(left_tip, left_dir, left.inner)
    crotch_r = _on_line(right_tip, right_dir, right.inner)
    valley = _dir_hit(left.flat_pt, left_dir, right.flat_pt, right_dir)
    return _clean_ring(
        [
            Vec2(left.outer, left_low),
            Vec2(left.inner, left_low),
            Vec2(left.inner, crotch_l),
            Vec2(*left_tip),
            Vec2(*right_tip),
            Vec2(right.inner, crotch_r),
            Vec2(right.inner, right_low),
            Vec2(right.outer, right_low),
            Vec2(right.outer, peak),
            Vec2(*right.flat_pt),
            Vec2(*valley),
            Vec2(*left.flat_pt),
            Vec2(left.outer, peak),
        ]
    )


def _stem_apex_outline(resolved: Resolved) -> GlyphOutline | None:
    if not any(join.type == "stem_apex" for join in resolved.skeleton.joins):
        return None
    return _seat_ring(resolved, _stem_apex_ring(resolved))


def _seat_ring(resolved: Resolved, ring: list[Vec2]) -> GlyphOutline:
    style = resolved.style
    raw = (tuple(ring),)
    holes = (False,)
    left = _side_amount(style, resolved.skeleton.sides[0])
    right = _side_amount(style, resolved.skeleton.sides[1])
    seated, ink_width = _seat_on_ink(raw, holes, left)
    return GlyphOutline(
        resolved.skeleton.glyph, left + ink_width + right, seated, holes, fair=False
    )


def _join_font_x(resolved: Resolved, join) -> float:
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    left, right = _closest_knots(by_id[join.a], by_id[join.b])
    return (
        _font_knot(by_id[join.a], resolved, left).x
        + _font_knot(by_id[join.b], resolved, right).x
    ) / 2.0


def _top_apex_joins(resolved: Resolved) -> list:
    by_id = {stroke.id: stroke for stroke in resolved.skeleton.strokes}
    return [
        join
        for join in resolved.skeleton.joins
        if join.type in ("apex", "apex_cut")
        and apex_meeting_y(by_id[join.a], by_id[join.b]) >= 0.5
    ]


def _lift_top_apex(contour, resolved: Resolved):
    """天の apex 接合に一番近い、キャップ上の平らな縁を、尖りの平切りに上げる。"""
    targets = [_join_font_x(resolved, join) for join in _top_apex_joins(resolved)]
    if not targets:
        return contour
    style = resolved.style
    cap = style.cap_height
    full = resolved.pen.stem * cap
    flat = float(style.metrics["apex_flat"]) * full
    peak = cap + style.overshoot["apex"] * cap
    pts = list(contour)
    closed = len(pts) > 1 and (pts[0] - pts[-1]).length() < 1e-6
    if closed:
        pts = pts[:-1]
    count = len(pts)
    spans = []
    for index in range(count):
        start, end = pts[index - 1], pts[index]
        if abs(start.y - cap) > 1.0 or abs(end.y - cap) > 1.0:
            continue
        if abs(start.x - end.x) < 20.0:
            continue
        spans.append((index - 1, index, (start.x + end.x) / 2.0))
    if not spans:
        return contour
    used: set[tuple[int, int]] = set()
    for target in targets:
        left_i, right_i, mid = min(spans, key=lambda item: abs(item[2] - target))
        left_i %= count
        right_i %= count
        if (left_i, right_i) in used:
            continue
        used.add((left_i, right_i))
        if pts[left_i].x > pts[right_i].x:
            left_i, right_i = right_i, left_i
        pts[left_i] = Vec2(mid - flat / 2.0, peak)
        pts[right_i] = Vec2(mid + flat / 2.0, peak)
    if closed:
        pts.append(pts[0])
    return tuple(pts)


def build_glyph(resolved: Resolved) -> GlyphOutline:
    resolved = _seat_arms(_raise_bars(resolved))
    stemmed = _stem_apex_outline(resolved)
    if stemmed is not None:
        return stemmed
    strokes = resolved.skeleton.strokes
    samples: dict[str, list[tuple[Vec2, Vec2]]] = {}
    widths: dict[str, list[float]] = {}
    frames, _shrink = _fit_bowls(resolved)
    for stroke in strokes:
        samples[stroke.id], widths[stroke.id] = _centerline(
            stroke,
            _stroke_resolved(stroke, resolved),
            frames.get(stroke.id),
            hug=not _nib_bowl(stroke, resolved),
        )
    _apply_joins(samples, widths, resolved)
    _extend_bowl_stems(samples, widths, resolved)
    contrast = any(_nib_bowl(stroke, resolved) for stroke in strokes)
    apices = _apex_joins(resolved)
    upright = _upright_apex_joins(resolved)
    apex_ids = {join.a for join in apices} | {join.b for join in apices}
    apex_ids |= {join.a for join in upright} | {join.b for join in upright}
    paths: list[Path] = []
    for apex in apices:
        paths.extend(_apex_paths(resolved, apex))
    for apex in upright:
        paths.extend(_up_apex_paths(resolved, apex))
    for stroke in strokes:
        if stroke.id in apex_ids:
            continue
        if _nib_bowl(stroke, resolved):
            paths.append(
                _contrast_path(stroke, resolved, frames[stroke.id], samples, widths)
            )
        else:
            paths.extend(
                _stroke_paths(
                    stroke,
                    samples[stroke.id],
                    widths[stroke.id],
                    _stroke_resolved(stroke, resolved),
                )
            )
    united = _union_all(paths)
    raw = [
        tuple(Vec2(x, y) for x, y in contour_points(c)) for c in split_contours(united)
    ]
    raw = _filter_contours(raw, resolved.style.micro_area_floor)
    if not raw:
        raise ValueError(f"{resolved.skeleton.glyph}: empty outline")
    largest = max(range(len(raw)), key=lambda i: abs(_signed_area(raw[i])))
    sign = 1.0 if _signed_area(raw[largest]) >= 0.0 else -1.0
    holes = tuple(_signed_area(c) * sign < 0.0 for c in raw)
    # 閉じた碗（O・0）の頂のヘアラインは、凍結したコントラストの計測そのものなので埋めない。
    crown = (
        (lambda pts: pts)
        if any(stroke.closed for stroke in strokes)
        else fill_crown_saddle
    )

    def _finish(contour: list[Vec2]) -> list[Vec2]:
        polished = list(contour)
        # 碗に付いた斜めの脚は、先端の切り口ではない。谷を削ると脚が欠ける。
        leg = any(stroke.role == "bowl" for stroke in strokes) and _has_diagonal_foot(
            resolved
        )
        if _apex_join(resolved) is None and not upright and not leg:
            polished = trim_apex_stub(bevel_apex_valley(polished))
        # 断面の碗が作る谷は、深い埋め直しをすると肩が太くなる。先に浅く面を取る。
        if contrast:
            polished = ease_outer_cusp(polished)
        polished = crown(smooth_side_pinches(polished))
        # 開いた高コントラストの腕（S。のちに C G 2 3 5）だけ、天地の直線を弧にする。
        if _open_nib_arm(resolved):
            polished = arc_open_crown(polished)
        # 閉じた碗の頂はコントラストの計測そのものなので、尖りも埋めない。
        polished = (
            blunt_inner_peak(polished) if crown is fill_crown_saddle else polished
        )
        if sum(join.type == "bowl_join" for join in resolved.skeleton.joins) >= 2:
            polished = fillet_bowl_waist(
                polished, pinch=0.08 * resolved.style.cap_height
            )
            polished = ease_level_shoulders(polished)
        return polished

    mid_y = resolved.style.cap_height / 2.0
    # 断面から描いた穴は、すでに凸なので角を丸め直さない。
    raw = tuple(
        tuple(_finish(list(contour)))
        if not hole
        else tuple(contour)
        if contrast
        else tuple(fair_bar_joins(list(contour), mid_y=mid_y))
        for contour, hole in zip(raw, holes)
    )
    style = resolved.style
    if len(apices) >= 2:
        raw = tuple(
            tuple(_flatten_shared_cap(list(contour), style.cap_height))
            if not hole
            else contour
            for contour, hole in zip(raw, holes, strict=True)
        )
    raw = tuple(
        _lift_top_apex(contour, resolved) if not hole else contour
        for contour, hole in zip(raw, holes, strict=True)
    )
    # 側面は骨格の箱ではなく、できた墨の外側に足す。碗を細くした分は墨の幅に入っている。
    left = _side_amount(style, resolved.skeleton.sides[0])
    right = _side_amount(style, resolved.skeleton.sides[1])
    seated, ink_width = _seat_on_ink(raw, holes, left)
    beak = style.terminals.get("open") == "beak" and any(
        "open" in stroke.ends for stroke in resolved.skeleton.strokes
    )
    return GlyphOutline(
        resolved.skeleton.glyph, left + ink_width + right, seated, holes, fair=beak
    )
