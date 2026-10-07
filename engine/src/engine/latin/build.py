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
from engine.latin.bowls import contrast_polygon, ease_outer_cusp
from engine.latin.hobby import Cubic, expand_stroke
from engine.latin.joins import (
    bevel_apex_valley,
    blunt_inner_peak,
    deepen_outer_waist,
    fair_bar_joins,
    fill_crown_saddle,
    retract_end,
    smooth_side_pinches,
    taper_end,
    trim_apex_stub,
)
from engine.latin.load import Resolved
from engine.latin.pens import half_width
from engine.latin.schema import Knot, Stroke
from engine.latin.terminals import terminal_polygon

_SAMPLES = 96


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
    if stroke.role != "bowl" or _bowl_joined(stroke, resolved):
        return 0.0
    return resolved.style.overshoot["round"] * resolved.style.cap_height


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
    for _pos, tangent in samples:
        angle = math.atan2(tangent.y, tangent.x)
        widths.append(half_width(resolved.pen, stroke.role, angle) * cap)
    factor = resolved.style.joins["crotch_thin"]
    ends = {stroke.ends[0], stroke.ends[1]}
    crotch = any(
        join.type == "crotch" and stroke.id in (join.a, join.b)
        for join in resolved.skeleton.joins
    )
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
) -> tuple[_Box, _Box]:
    """中心線と、太さを付けた外形の (xmin, xmax, ymin, ymax)。

    level では水平に走る所だけで測る。曲がり始めの膨らみはオーバーシュートとして残る。
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
        target_y = (-overshoot, cap + overshoot)
        frame = _plain_frame(group[0], resolved)
        closed = group[0].closed
        target_x = None
        # 断面から描く碗の外形は、一番細い幅だけ外へ出る。位置合わせもその幅で測る。
        contrast = resolved.pen.type == "nib" and _bowl_joined(group[0], resolved)
        if closed:
            _line, ink = _boxes([_centerline(s, resolved, frame) for s in group])
            ratio = (ink[1] - ink[0]) / (ink[3] - ink[2])
            target_x = (ink[0], ink[0] + ratio * (target_y[1] - target_y[0]))
            shrink = max(shrink, ink[1] - target_x[1])
        for _ in range(4):
            built = [_centerline(s, resolved, frame, hug=not contrast) for s in group]
            if contrast:
                built = [
                    (samples, [min(widths)] * len(widths)) for samples, widths in built
                ]
            line, ink = _boxes(built, level=_bowl_joined(group[0], resolved))
            y_off, y_scale = _refit(
                frame.y_off, frame.y_scale, line[2], line[3], ink[2], ink[3], target_y
            )
            x_off, x_scale = frame.x_off, frame.x_scale
            if target_x is not None:
                x_off, x_scale = _refit(
                    x_off, x_scale, line[0], line[1], ink[0], ink[1], target_x
                )
            frame = _Frame(x_off, x_scale, y_off, y_scale)
        for stroke in group:
            frames[stroke.id] = frame
    return frames, shrink


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
        path = _to_path(variable_width_outline(ext_samples, ext_widths, close=True))
        for box in boxes:
            path = _difference(path, _to_path(box))
        paths.append(path)
        paths.extend(_to_path(poly) for poly in serifs)
        skip = {index for index, *_rest in diagonal}
        paths.extend(_terminal_paths(samples, widths, stroke, resolved, skip=skip))
        return paths
    paths.extend(_terminal_paths(samples, widths, stroke, resolved))
    return paths


_CUT_KINDS = ("flat", "apex_sharp", "apex_cut")
_SERIF_KINDS = ("serif_bracketed", "serif_hairline", "spur")


def _diagonal_ends(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    stroke: Stroke,
    resolved: Resolved,
) -> list[tuple[int, str, Vec2, Vec2, float]]:
    """斜めに入る端。切り口は水平にそろえる。"""
    found: list[tuple[int, str, Vec2, Vec2, float]] = []
    last = len(samples) - 1
    for index, sign, tag in ((0, -1.0, stroke.ends[0]), (last, 1.0, stroke.ends[1])):
        kind = resolved.style.terminals[tag]
        if kind not in _CUT_KINDS + _SERIF_KINDS:
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
    # 画の傾きに沿った平行四辺形。水平な矩形だと、片側だけ垂直なくさびになる。
    top_lo, top_hi = center(face) - span, center(face) + span
    bot_lo, bot_hi = center(back) - span, center(back) + span
    polys = [
        [Vec2(top_lo, face), Vec2(top_hi, face), Vec2(bot_hi, back), Vec2(bot_lo, back)]
    ]
    if kind == "serif_hairline":
        reach = max(thick * 2.5, 8.0)
    elif kind == "serif_bracketed":
        reach = max(style.metrics.get("bracket", 0.0) * cap, thick)
    else:
        reach = 0.0
    if reach > 0.0:
        inner = back - sign * reach
        mid = center(inner)
        polys.append(
            [
                Vec2(bot_lo, back),
                Vec2(bot_hi, back),
                Vec2(mid + cross, inner),
                Vec2(mid - cross, inner),
            ]
        )
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
            if kind not in (
                "flat",
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


def build_glyph(resolved: Resolved) -> GlyphOutline:
    strokes = resolved.skeleton.strokes
    samples: dict[str, list[tuple[Vec2, Vec2]]] = {}
    widths: dict[str, list[float]] = {}
    frames, _shrink = _fit_bowls(resolved)
    for stroke in strokes:
        samples[stroke.id], widths[stroke.id] = _centerline(
            stroke, resolved, frames.get(stroke.id), hug=not _nib_bowl(stroke, resolved)
        )
    _apply_joins(samples, widths, resolved)
    _extend_bowl_stems(samples, widths, resolved)
    contrast = any(_nib_bowl(stroke, resolved) for stroke in strokes)
    paths = []
    for stroke in strokes:
        if _nib_bowl(stroke, resolved):
            paths.append(
                _contrast_path(stroke, resolved, frames[stroke.id], samples, widths)
            )
        else:
            paths.extend(
                _stroke_paths(stroke, samples[stroke.id], widths[stroke.id], resolved)
            )
    united = _union_all(paths)
    raw = [
        tuple(Vec2(x, y) for x, y in contour_points(c)) for c in split_contours(united)
    ]
    floor = resolved.style.micro_area_floor
    raw = tuple(c for c in raw if len(c) >= 3 and abs(_signed_area(c)) >= floor)
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
        polished = trim_apex_stub(bevel_apex_valley(list(contour)))
        # 断面の碗が作る谷は、深い埋め直しをすると肩が太くなる。先に浅く面を取る。
        if contrast:
            polished = ease_outer_cusp(polished)
        polished = crown(smooth_side_pinches(polished))
        # 閉じた碗の頂はコントラストの計測そのものなので、尖りも埋めない。
        polished = (
            blunt_inner_peak(polished) if crown is fill_crown_saddle else polished
        )
        if resolved.style.name == "modern" and resolved.skeleton.glyph == "B":
            polished = deepen_outer_waist(polished)
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
    # 側面は骨格の箱ではなく、できた墨の外側に足す。碗を細くした分は墨の幅に入っている。
    left = _side_amount(style, resolved.skeleton.sides[0])
    right = _side_amount(style, resolved.skeleton.sides[1])
    seated, ink_width = _seat_on_ink(raw, holes, left)
    return GlyphOutline(
        resolved.skeleton.glyph, left + ink_width + right, seated, holes
    )
