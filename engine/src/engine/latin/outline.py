"""折れ線輪郭を cubic にフィットし、直線スナップと開始点を固定する。"""

from __future__ import annotations

import math

from pathops import Path, simplify

from engine.curve_fit import ContourPath, fit_closed_contour, hausdorff_path_to_polyline
from engine.join_solver import count_contours
from engine.latin.build import GlyphOutline
from engine.latin.style import Style


def _signed_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1] - points[j][0] * points[i][1]
    return 0.5 * area


def _rotate_start(path: ContourPath) -> ContourPath:
    points = path.on_curve_points()
    if len(points) < 2 or len(path.segs) != len(points):
        return path
    index = min(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    if index == 0:
        return path
    return ContourPath(start=points[index], segs=path.segs[index:] + path.segs[:index])


def _near_axis(dx: float, dy: float, tol_deg: float) -> str | None:
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
    if angle > 90.0:
        angle = 180.0 - angle
    if angle <= tol_deg:
        return "h"
    if abs(90.0 - angle) <= tol_deg:
        return "v"
    return None


def _flat_enough(start: tuple[float, float], seg: tuple, end: tuple[float, float]) -> bool:
    """曲線でも、制御点が弦から 1 ユニット以内なら直線とみなす。"""
    if seg[0] == "L":
        return True
    chord_x = end[0] - start[0]
    chord_y = end[1] - start[1]
    length = math.hypot(chord_x, chord_y) or 1.0
    for cx, cy in ((seg[1], seg[2]), (seg[3], seg[4])):
        cross = abs((cx - start[0]) * chord_y - (cy - start[1]) * chord_x) / length
        if cross > 1.0:
            return False
    return True


def _snap(path: ContourPath, tol_deg: float) -> ContourPath:
    """すでに直線の区間だけ、軸から tol 度以内なら水平または垂直にする。"""
    points = path.on_curve_points()
    if len(points) < 2 or len(path.segs) != len(points):
        return path
    snapped = [points[0]]
    segs: list[tuple] = []
    for i, seg in enumerate(path.segs):
        start = snapped[-1]
        end = points[(i + 1) % len(points)]
        kind = _near_axis(end[0] - start[0], end[1] - start[1], tol_deg)
        if kind is not None and _flat_enough(start, seg, end):
            if kind == "h":
                end = (end[0], start[1])
            else:
                end = (start[0], end[1])
            segs.append(("L", end[0], end[1]))
        elif seg[0] == "L":
            segs.append(("L", end[0], end[1]))
        else:
            segs.append(("C", seg[1], seg[2], seg[3], seg[4], end[0], end[1]))
        snapped.append(end)
    return ContourPath(start=snapped[0], segs=segs)


def _round(path: ContourPath) -> ContourPath:
    def r(x: float, y: float) -> tuple[float, float]:
        return (float(round(x)), float(round(y)))

    return path.transform(r)


def _orient(path: ContourPath, *, hole: bool) -> ContourPath:
    area = _signed_area(path.on_curve_points())
    # Y 上向き。外形は反時計回り（正）、穴は時計回り（負）。
    if hole and area > 0.0:
        return path.reversed()
    if not hole and area < 0.0:
        return path.reversed()
    return path


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _split_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[tuple, tuple]:
    a = _lerp(p0, p1, t)
    b = _lerp(p1, p2, t)
    c = _lerp(p2, p3, t)
    d = _lerp(a, b, t)
    e = _lerp(b, c, t)
    f = _lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def _axis_roots(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    axis: int,
) -> list[float]:
    """導関数（二次）の根。端に十分近いものは、端の点が極値とみなす。"""
    a0, a1, a2, a3 = p0[axis], p1[axis], p2[axis], p3[axis]
    quad_a = -a0 + 3.0 * a1 - 3.0 * a2 + a3
    quad_b = 2.0 * a0 - 4.0 * a1 + 2.0 * a2
    quad_c = a1 - a0
    roots: list[float] = []
    if abs(quad_a) < 1e-8:
        if abs(quad_b) > 1e-8:
            roots.append(-quad_c / quad_b)
    else:
        disc = quad_b * quad_b - 4.0 * quad_a * quad_c
        if disc >= 0.0:
            root = math.sqrt(disc)
            roots.append((-quad_b + root) / (2.0 * quad_a))
            roots.append((-quad_b - root) / (2.0 * quad_a))
    return [t for t in roots if 1e-3 < t < 1.0 - 1e-3]


def _near(point: tuple[float, float], ring: list[tuple[float, float]]) -> float:
    best = float("inf")
    n = len(ring)
    for index in range(n):
        start, end = ring[index], ring[(index + 1) % n]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = dx * dx + dy * dy
        t = 0.0 if length < 1e-12 else max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length))
        qx, qy = start[0] + dx * t, start[1] + dy * t
        best = min(best, math.hypot(point[0] - qx, point[1] - qy))
    return best


def _shorter_chain(
    ring: list[tuple[float, float]],
    start: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    def index_of(point: tuple[float, float]) -> int:
        return min(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - point[0], ring[i][1] - point[1]))

    i0, i1 = index_of(start), index_of(end)
    chains: list[list[int]] = []
    for begin, stop in ((i0, i1), (i1, i0)):
        chain = [begin]
        index = begin
        while index != stop and len(chain) <= len(ring):
            index = (index + 1) % len(ring)
            chain.append(index)
        chains.append(chain)
    chosen = min(chains, key=len)
    if chosen[0] != i0:
        chosen = list(reversed(chosen))
    return [ring[index] for index in chosen]


def _point_line_dist(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs((point[0] - start[0]) * dy - (point[1] - start[1]) * dx) / length


def _thin_chain(
    chain: list[tuple[float, float]],
    limit: float,
) -> list[tuple[float, float]]:
    """弦から limit 以内の点を落とし、誤差を保ったまま節点を減らす。"""
    if len(chain) <= 2:
        return chain
    index = max(range(1, len(chain) - 1), key=lambda i: _point_line_dist(chain[i], chain[0], chain[-1]))
    if _point_line_dist(chain[index], chain[0], chain[-1]) <= limit:
        return [chain[0], chain[-1]]
    left = _thin_chain(chain[: index + 1], limit)
    right = _thin_chain(chain[index:], limit)
    return left[:-1] + right


def _repair_strays(path: ContourPath, points: list[tuple[float, float]], limit: float) -> ContourPath:
    """折れ線から limit より離れる cubic は、誤差以内まで間引いた折れ線に戻す。"""
    ring = points[:-1] if len(points) > 1 and points[0] == points[-1] else list(points)
    if len(ring) < 3:
        return path
    segs: list[tuple] = []
    cur = path.start
    for seg in path.segs:
        end = (float(seg[1]), float(seg[2])) if seg[0] == "L" else (float(seg[5]), float(seg[6]))
        stray = False
        if seg[0] == "C":
            p1 = (float(seg[1]), float(seg[2]))
            p2 = (float(seg[3]), float(seg[4]))
            stray = any(_near(_cubic_at(cur, p1, p2, end, t / 8.0), ring) > limit for t in range(1, 8))
        if stray:
            for point in _thin_chain(_shorter_chain(ring, cur, end), limit)[1:]:
                segs.append(("L", point[0], point[1]))
            if not segs or (segs[-1][1], segs[-1][2]) != end:
                segs.append(("L", end[0], end[1]))
        else:
            segs.append(seg)
        cur = end
    return ContourPath(start=path.start, segs=segs)


def _flatten_true_lines(path: ContourPath, points: list[tuple[float, float]], tol: float = 1.0) -> ContourPath:
    """元の折れ線が弦から tol 以内なら、膨らんだ cubic を直線に戻す。"""
    ring = points[:-1] if len(points) > 1 and points[0] == points[-1] else list(points)
    if len(ring) < 3:
        return path

    def index_of(point: tuple[float, float]) -> int:
        return min(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - point[0], ring[i][1] - point[1]))

    def straight(start: tuple[float, float], end: tuple[float, float]) -> bool:
        i0, i1 = index_of(start), index_of(end)
        if i0 == i1:
            return False
        chains = []
        for a, b in ((i0, i1), (i1, i0)):
            chain = [a]
            index = a
            while index != b and len(chain) <= len(ring):
                index = (index + 1) % len(ring)
                chain.append(index)
            chains.append(chain)
        chain = min(chains, key=len)
        if len(chain) < 2:
            return False
        chord_x, chord_y = end[0] - start[0], end[1] - start[1]
        length = math.hypot(chord_x, chord_y) or 1.0
        for index in chain:
            px, py = ring[index]
            cross = abs((px - start[0]) * chord_y - (py - start[1]) * chord_x) / length
            if cross > tol:
                return False
        return True

    segs: list[tuple] = []
    cur = path.start
    for seg in path.segs:
        end = (float(seg[1]), float(seg[2])) if seg[0] == "L" else (float(seg[5]), float(seg[6]))
        if seg[0] == "C" and straight(cur, end):
            segs.append(("L", end[0], end[1]))
        else:
            segs.append(seg)
        cur = end
    return ContourPath(start=path.start, segs=segs)


def _insert_extrema(path: ContourPath) -> ContourPath:
    """各 cubic の x・y 極値にオンカーブ点を置く。曲線の形は変えない。"""
    segs: list[tuple] = []
    cur = path.start
    for seg in path.segs:
        if seg[0] == "L":
            end = (float(seg[1]), float(seg[2]))
            segs.append(("L", end[0], end[1]))
            cur = end
            continue
        p1 = (float(seg[1]), float(seg[2]))
        p2 = (float(seg[3]), float(seg[4]))
        p3 = (float(seg[5]), float(seg[6]))
        roots = []
        for axis in (0, 1):
            for root in _axis_roots(cur, p1, p2, p3, axis):
                point = _cubic_at(cur, p1, p2, p3, root)
                if min(abs(point[axis] - cur[axis]), abs(point[axis] - p3[axis])) > 1.0:
                    roots.append(root)
        roots = sorted(set(roots))
        piece = (cur, p1, p2, p3)
        prev = 0.0
        for root in roots:
            local = (root - prev) / (1.0 - prev)
            if not 0.0 < local < 1.0:
                continue
            left, piece = _split_cubic(*piece, local)
            segs.append(("C", left[1][0], left[1][1], left[2][0], left[2][1], left[3][0], left[3][1]))
            prev = root
        segs.append(("C", piece[1][0], piece[1][1], piece[2][0], piece[2][1], piece[3][0], piece[3][1]))
        cur = p3
    return ContourPath(start=path.start, segs=segs)


def _skia(path: ContourPath) -> Path:
    skia = Path()
    skia.moveTo(*path.start)
    for seg in path.segs:
        if seg[0] == "L":
            skia.lineTo(float(seg[1]), float(seg[2]))
        else:
            skia.cubicTo(float(seg[1]), float(seg[2]), float(seg[3]), float(seg[4]), float(seg[5]), float(seg[6]))
    skia.close()
    return skia


def _cubic_at(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _missing_extrema(path: ContourPath) -> int:
    """丸め後に、端から 1 ユニットより離れた極値が残っていれば数える。"""
    cur = path.start
    missing = 0
    for seg in path.segs:
        if seg[0] != "C":
            cur = (float(seg[1]), float(seg[2]))
            continue
        p1 = (float(seg[1]), float(seg[2]))
        p2 = (float(seg[3]), float(seg[4]))
        p3 = (float(seg[5]), float(seg[6]))
        for axis in (0, 1):
            for root in _axis_roots(cur, p1, p2, p3, axis):
                point = _cubic_at(cur, p1, p2, p3, root)
                if min(abs(point[axis] - cur[axis]), abs(point[axis] - p3[axis])) > 1.0:
                    missing += 1
        cur = p3
    return missing


def fit_outline(outline: GlyphOutline, style: Style) -> tuple[ContourPath, ...]:
    """様式の誤差上限でフィットする。極値を入れ、丸め後に誤差と自己交差を見る。"""
    curve = style.curve
    limit = float(curve["max_error"]) + 0.75
    fitted: list[tuple[tuple[float, float], ContourPath]] = []
    for contour, hole in zip(outline.contours, outline.holes):
        points = [(p.x, p.y) for p in contour]
        path, _meta = fit_closed_contour(
            points,
            max_error_upm=float(curve["max_error"]),
            corner_deg=float(curve["corner_deg"]),
            max_anchors=int(curve["max_anchors_per_contour"]),
        )
        path = _repair_strays(path, points, float(curve["max_error"]))
        path = _flatten_true_lines(path, points)
        path = _round(_rotate_start(_insert_extrema(_snap(path, 0.5))))
        path = _orient(_rotate_start(path), hole=hole)
        error = hausdorff_path_to_polyline(path, points)
        if error > limit:
            raise ValueError(f"{outline.glyph}: fit error {error:.3f} > {limit:.3f}")
        skia = _skia(path)
        simplified = simplify(skia, fix_winding=True)
        if count_contours(skia) != count_contours(simplified):
            raise ValueError(f"{outline.glyph}: self-intersection after rounding")
        if _missing_extrema(path) > 0:
            raise ValueError(f"{outline.glyph}: extrema are not on-curve points")
        origin = min(path.on_curve_points(), key=lambda p: (p[1], p[0]))
        fitted.append((origin, path))
    fitted.sort(key=lambda item: (item[0][1], item[0][0]))
    return tuple(path for _origin, path in fitted)
