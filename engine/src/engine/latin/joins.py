"""接合。股の細め、頂点の谷埋め、腰のくびれ、幹への埋め込み。"""

from __future__ import annotations

import math
from itertools import pairwise

from engine.geometry import Vec2


def taper_end(half_widths: list[float], *, at_start: bool, factor: float, fraction: float = 0.22) -> None:
    """端の半幅を factor 倍へ滑らかに寄せる。factor が 1 なら変えない。"""
    if factor == 1.0 or len(half_widths) < 3:
        return
    span = max(2, int(len(half_widths) * fraction))
    if at_start:
        for i in range(span):
            blend = 1.0 - i / span
            half_widths[i] *= (1.0 - blend) + factor * blend
        return
    last = len(half_widths) - 1
    for i in range(span):
        blend = 1.0 - i / span
        half_widths[last - i] *= (1.0 - blend) + factor * blend


def _closest(point: Vec2, samples: list[tuple[Vec2, Vec2]]) -> tuple[float, Vec2, int] | None:
    best: tuple[float, Vec2, int] | None = None
    for i in range(len(samples) - 1):
        start = samples[i][0]
        end = samples[i + 1][0]
        chord = end - start
        length2 = chord.dot(chord)
        if length2 < 1e-12:
            proj = start
        else:
            t = max(0.0, min(1.0, (point - start).dot(chord) / length2))
            proj = start + chord * t
        dist = (point - proj).length()
        if best is None or dist < best[0]:
            best = (dist, proj, i)
    return best


def retract_end(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    partner: list[tuple[Vec2, Vec2]],
    partner_widths: list[float],
    *,
    at_start: bool,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    """端が相手の中心線を越えていたら、中心線との交点まで戻す。"""
    if len(samples) < 3 or len(partner) < 2:
        return samples, widths
    end_i = 0 if at_start else len(samples) - 1
    hit = _closest(samples[end_i][0], partner)
    if hit is None:
        return samples, widths
    dist, center, seg = hit
    partner_half = partner_widths[min(seg, len(partner_widths) - 1)]
    # 相手の太さ程度までは埋め込む。幹の端が交差する横画まで届く距離にはしない。
    reach = 1.5 * (widths[end_i] + partner_half)
    if dist > reach:
        return samples, widths
    normal = samples[len(samples) // 2][0] - center
    if normal.length() < 1e-6:
        return samples, widths
    normal = normal.normalized()

    def side(point: Vec2) -> float:
        return (point - center).dot(normal)

    pts = list(samples)
    ws = list(widths)
    if at_start:
        k = 0
        while k < len(pts) - 1 and side(pts[k][0]) < 0.0:
            k += 1
        if k == 0:
            return samples, widths
        p0, p1 = pts[k - 1][0], pts[k][0]
        s0, s1 = side(p0), side(p1)
        t = 0.0 if abs(s1 - s0) < 1e-9 else max(0.0, min(1.0, -s0 / (s1 - s0)))
        pos = p0.lerp(p1, t)
        return [(pos, pts[k][1])] + pts[k:], [ws[k - 1] + (ws[k] - ws[k - 1]) * t] + ws[k:]
    k = len(pts) - 1
    while k > 0 and side(pts[k][0]) < 0.0:
        k -= 1
    if k == len(pts) - 1:
        return samples, widths
    p0, p1 = pts[k][0], pts[k + 1][0]
    s0, s1 = side(p0), side(p1)
    t = 0.0 if abs(s1 - s0) < 1e-9 else max(0.0, min(1.0, -s0 / (s1 - s0)))
    pos = p0.lerp(p1, t)
    return pts[: k + 1] + [(pos, pts[k][1])], ws[: k + 1] + [ws[k] + (ws[k + 1] - ws[k]) * t]


def _ring(points: list[Vec2]) -> list[Vec2]:
    if len(points) > 1 and points[0].x == points[-1].x and points[0].y == points[-1].y:
        return points[:-1]
    return list(points)


def _turn(a: Vec2, b: Vec2, c: Vec2) -> float:
    v1 = b - a
    v2 = c - b
    return math.degrees(math.atan2(v1.cross(v2), v1.dot(v2)))


def _walk(points: list[Vec2], start: int, step: int, reach: float) -> int:
    acc = 0.0
    index = start
    n = len(points)
    for _ in range(n - 2):
        nxt = (index + step) % n
        acc += (points[nxt] - points[index]).length()
        index = nxt
        if acc >= reach:
            break
    return index


def _chain_through(points: list[Vec2], start: int, end: int, must: int) -> list[int] | None:
    n = len(points)
    chain = [start]
    index = start
    while index != end:
        index = (index + 1) % n
        chain.append(index)
        if len(chain) > n:
            return None
    if must not in chain:
        return None
    return chain


def _chord_depth(point: Vec2, start: Vec2, end: Vec2) -> float:
    chord = end - start
    length = chord.length()
    if length < 1e-6:
        return 0.0
    return abs((point - start).cross(chord)) / length


def _replace_chain(points: list[Vec2], chain: list[int], bridge: list[Vec2]) -> list[Vec2]:
    """chain の内側を bridge に替える。輪郭の順は保つ。"""
    out = [points[chain[0]], *bridge]
    index = chain[-1]
    n = len(points)
    while index != chain[0]:
        out.append(points[index])
        index = (index + 1) % n
        if len(out) > n + len(bridge) + 2:
            return points
    return out


def _tangent_bridge(points: list[Vec2], chain: list[int]) -> list[Vec2]:
    """残した側の接線で、くびれを三次曲線でつなぐ。"""
    n = len(points)
    start = points[chain[0]]
    end = points[chain[-1]]
    into = start - points[(chain[0] - 1) % n]
    out = points[(chain[-1] + 1) % n] - end
    if into.length() < 1e-6 or out.length() < 1e-6:
        return []
    into = into.normalized()
    out = out.normalized()
    span = (end - start).length()
    control = span * 0.35
    c1 = start + into * control
    c2 = end - out * control
    samples: list[Vec2] = []
    for step in range(1, 7):
        t = step / 7.0
        u = 1.0 - t
        samples.append(start * (u**3) + c1 * (3 * u * u * t) + c2 * (3 * u * t * t) + end * (t**3))
    return samples


def _off_horizontal(delta: Vec2) -> float:
    off = abs(math.degrees(math.atan2(delta.y, delta.x)))
    return min(off, 180.0 - off)


def _tangent_corner(origin: Vec2, start_tan: Vec2, end: Vec2, end_tan: Vec2) -> Vec2 | None:
    """始点と終点の接線が交わる点。二次曲線はこの点を制御点にすると変曲しない。"""
    denom = start_tan.cross(end_tan)
    if abs(denom) < 1e-8:
        return None
    along = (end - origin).cross(end_tan) / denom
    if not 4.0 <= along <= 180.0:
        return None
    control = origin + start_tan * along
    if (end - control).dot(end_tan) < 4.0:
        return None
    return control


def _quadratic(start: Vec2, control: Vec2, end: Vec2) -> list[Vec2]:
    samples: list[Vec2] = []
    for step in range(1, 12):
        t = step / 12.0
        u = 1.0 - t
        samples.append(start * (u * u) + control * (2.0 * u * t) + end * (t * t))
    return samples


def _long_horizontals(points: list[Vec2]) -> list[tuple[float, int, int]]:
    found: list[tuple[float, int, int]] = []
    n = len(points)
    for index in range(n):
        start, end = points[index], points[(index + 1) % n]
        if abs(end.x - start.x) < 40.0 or abs(end.y - start.y) > 1.2:
            continue
        found.append(((start.y + end.y) / 2.0, index, (index + 1) % n))
    return found


def fair_bar_joins(points: list[Vec2], *, mid_y: float) -> list[Vec2]:
    """横棒から碗へ入る内周の凹みと角だけを、横棒に接する曲線で置き換える。

    中央の横棒と、上下の山が天と地の横棒へ入る角が対象。碗の途中の太さは変えない。
    """
    pts = _ring(points)
    if len(pts) < 8:
        return pts
    edges = _long_horizontals(pts)
    if not edges:
        return pts
    mid = min(edges, key=lambda item: abs(item[0] - mid_y))
    floor = min(edges, key=lambda item: item[0])
    ceiling = max(edges, key=lambda item: item[0])
    if abs(mid[0] - mid_y) <= 100.0:
        pts = _fair_at_height(pts, mid[0])
    long = {"min_side": 56.0, "min_arc": 70.0, "reach": 240.0}
    if floor[0] < mid_y - 80.0 and abs(floor[0] - mid[0]) > 20.0:
        pts = _fair_at_height(pts, floor[0], **long)
    if ceiling[0] > mid_y + 80.0 and abs(ceiling[0] - mid[0]) > 20.0:
        pts = _fair_at_height(pts, ceiling[0], **long)
    return pts


def _fair_at_height(
    points: list[Vec2],
    height: float,
    *,
    min_side: float = 16.0,
    min_arc: float = 28.0,
    reach: float = 160.0,
) -> list[Vec2]:
    edges = _long_horizontals(points)
    if not edges:
        return points
    _y, index, nxt = min(edges, key=lambda item: abs(item[0] - height))
    if abs(_y - height) > 8.0:
        return points
    return _fair_horizontal(points, index, nxt, min_side=min_side, min_arc=min_arc, reach=reach)


def _fair_horizontal(
    points: list[Vec2],
    index: int,
    nxt: int,
    *,
    min_side: float = 16.0,
    min_arc: float = 28.0,
    reach: float = 160.0,
) -> list[Vec2]:
    pts = _ring(points)
    n = len(pts)
    if n < 8 or nxt != (index + 1) % n:
        return pts
    start, end = pts[index], pts[nxt]
    if end.x >= start.x:
        junction, step, origin = nxt, 1, end
    else:
        junction, step, origin = index, -1, start
    first = pts[(junction + step) % n] - origin
    if first.length() < 1e-6:
        return pts
    ymin = min(point.y for point in pts)
    ymax = max(point.y for point in pts)
    bowl_up = abs(origin.y - ymin) <= abs(origin.y - ymax)

    def side(point: Vec2) -> float:
        return point.y - origin.y if bowl_up else origin.y - point.y

    path = [junction]
    acc = [0.0]
    cursor = junction
    while acc[-1] < reach:
        ahead = (cursor + step) % n
        acc.append(acc[-1] + (pts[ahead] - pts[cursor]).length())
        path.append(ahead)
        cursor = ahead
        if cursor == junction:
            break
    sides = [side(pts[at]) for at in path]
    if _off_horizontal(first) <= 8.0 and min(sides) >= -2.0:
        return pts
    start_tan = Vec2(1.0, 0.0) if pts[(junction + step) % n].x >= origin.x - 0.5 else Vec2(-1.0, 0.0)
    landing: int | None = None
    control: Vec2 | None = None
    for at in range(1, len(path)):
        if acc[at] < min_arc or sides[at] < min_side or acc[at] > reach - 10.0:
            continue
        here = path[at]
        prev = pts[path[at - 1]]
        after = pts[(here + step) % n]
        if abs(_turn(prev, pts[here], after)) > 12.0:
            continue
        end_tan = after - pts[here]
        if end_tan.length() < 1e-6:
            continue
        corner = _tangent_corner(origin, start_tan, pts[here], end_tan.normalized())
        if corner is None or side(corner) < -1.0:
            continue
        landing = here
        control = corner
        break
    if landing is None or control is None:
        return pts
    samples = _quadratic(origin, control, pts[landing])
    if min(side(point) for point in samples) < -1.0:
        return pts
    walk = [junction]
    cursor = junction
    while cursor != landing:
        cursor = (cursor + step) % n
        walk.append(cursor)
        if len(walk) > n:
            return pts
    if step == 1:
        chain, bridge = walk, samples
    else:
        chain, bridge = list(reversed(walk)), list(reversed(samples))
    return _replace_chain(pts, chain, bridge)


def _level_edge(a: Vec2, b: Vec2) -> bool:
    dx = abs(b.x - a.x)
    return dx > 6.0 and abs(b.y - a.y) < dx * 0.05


def _notch(t: float) -> float:
    """端では傾きを戻し、底だけを狭く曲げる。"""
    if abs(t) >= 1.0:
        return 0.0
    return math.cos(math.pi * t / 2.0) ** 3


def _x_on(span: list[Vec2], y: float) -> float:
    for left, right in pairwise(span):
        if abs(right.y - left.y) < 1e-6:
            continue
        if (left.y - y) * (right.y - y) <= 0.0:
            along = (y - left.y) / (right.y - left.y)
            return left.x + (right.x - left.x) * along
    return min(span, key=lambda point: abs(point.y - y)).x


def deepen_outer_waist(points: list[Vec2], *, depth: float = 30.0, half: float = 40.0) -> list[Vec2]:
    """右の二つの山のあいだだけ、外側の谷を鋭く左へ寄せる。内周は動かさない。"""
    pts = _ring(points)
    n = len(pts)
    if n < 8:
        return pts
    ymin = min(point.y for point in pts)
    ymax = max(point.y for point in pts)
    span = ymax - ymin
    if span < 40.0:
        return pts
    right = max(point.x for point in pts)
    mid = (ymin + ymax) / 2.0
    band = [index for index, point in enumerate(pts) if point.x > right - 110.0 and abs(point.y - mid) < span * 0.28]
    if len(band) < 3:
        return pts
    waist_at = min(band, key=lambda index: pts[index].x)
    waist = pts[waist_at]
    if not any(point.y > waist.y + 50.0 and point.x > waist.x + 16.0 for point in pts):
        return pts
    if not any(point.y < waist.y - 50.0 and point.x > waist.x + 16.0 for point in pts):
        return pts

    def outside(index: int) -> bool:
        point = pts[index]
        return abs(point.y - waist.y) > half or point.x < waist.x - 10.0

    def edge(step: int) -> int:
        cursor = waist_at
        for _ in range(n // 3):
            nxt = (cursor + step) % n
            if outside(nxt):
                return nxt
            cursor = nxt
        return cursor

    start, end = edge(-1), edge(1)
    chain = [start]
    cursor = start
    while cursor != end:
        cursor = (cursor + 1) % n
        chain.append(cursor)
        if len(chain) > n // 2:
            return pts
    span_pts = [pts[index] for index in chain]
    if abs(span_pts[-1].y - span_pts[0].y) < 12.0:
        return pts
    steps = max(10, int(abs(span_pts[-1].y - span_pts[0].y) / 4.0))
    bridge: list[Vec2] = []
    for step in range(1, steps):
        y = span_pts[0].y + (span_pts[-1].y - span_pts[0].y) * step / steps
        bridge.append(Vec2(_x_on(span_pts, y) - depth * _notch((y - waist.y) / half), y))
    return _replace_chain(pts, chain, bridge)


def smooth_side_pinches(points: list[Vec2], *, turn_lim: float = -100.0, reach: float = 70.0) -> list[Vec2]:
    """横から入った鋭いくびれだけを弧で埋める。上下に開いた股は触らない。"""
    pts = _ring(points)
    if len(pts) < 8:
        return pts
    for _ in range(4):
        n = len(pts)
        replaced = False
        for i in range(n):
            if _turn(pts[(i - 1) % n], pts[i], pts[(i + 1) % n]) > turn_lim:
                continue
            if _level_edge(pts[(i - 1) % n], pts[i]) or _level_edge(pts[i], pts[(i + 1) % n]):
                # セリフの下面と画の付け根。くびれではない。
                continue
            chain = _chain_through(pts, _walk(pts, i, -1, reach), _walk(pts, i, 1, reach), i)
            if chain is None or len(chain) < 3:
                continue
            start, end = pts[chain[0]], pts[chain[-1]]
            if abs(end.y - start.y) < abs(end.x - start.x) * 1.5:
                continue
            if _chord_depth(pts[i], start, end) < 25.0:
                continue
            pts = _replace_chain(pts, chain, _tangent_bridge(pts, chain))
            replaced = True
            break
        if not replaced:
            break
    return pts


def blunt_inner_peak(points: list[Vec2], *, band: float = 50.0, gap: float = 6.0) -> list[Vec2]:
    """外の端より内側で、カウンターに突き出した尖りを隣との弦まで落とす。"""
    pts = _ring(points)
    n = len(pts)
    if n < 8:
        return pts
    ymax = max(point.y for point in pts)
    ymin = min(point.y for point in pts)
    out = list(pts)
    for index in range(n):
        point = pts[index]
        prev = pts[index - 1]
        nxt = pts[(index + 1) % n]
        if abs(_turn(prev, point, nxt)) < 30.0 or abs(nxt.x - prev.x) < 1.0:
            continue
        high = point.y > ymax - band and point.y < ymax - gap and prev.y < point.y - 2.0 and nxt.y < point.y - 2.0
        low = point.y < ymin + band and point.y > ymin + gap and prev.y > point.y + 2.0 and nxt.y > point.y + 2.0
        if not high and not low:
            continue
        t = (point.x - prev.x) / (nxt.x - prev.x)
        t = min(1.0, max(0.0, t))
        out[index] = Vec2(point.x, prev.y + (nxt.y - prev.y) * t)
    return out


def fill_crown_saddle(points: list[Vec2], *, depth: float = 40.0, gap: float = 30.0) -> list[Vec2]:
    """上下の端で、2つの肩のあいだに浅く沈んだ所を肩から肩への直線で埋める。

    細い方向が水平のペンでは、ヘアラインの両側の太りが外へも膨らみ、頂が鞍形に凹む。
    """
    pts = _ring(points)
    for sign in (1.0, -1.0):
        n = len(pts)
        if n < 8:
            return pts
        height = [point.y * sign for point in pts]
        top = max(range(n), key=height.__getitem__)
        best: list[int] | None = None
        for j in range(n):
            if j == top or abs(pts[j].x - pts[top].x) < gap or height[j] < height[top] - depth:
                continue
            if height[j] < height[j - 1] or height[j] < height[(j + 1) % n]:
                continue
            floor = height[j]
            lo, hi = sorted((pts[top].x, pts[j].x))
            for a, b in ((top, j), (j, top)):
                chain = _chain_through(pts, a, b, a)
                if chain is None or len(chain) < 3:
                    continue
                inner = chain[1:-1]
                sink = min(height[k] for k in inner)
                if not floor - depth <= sink < floor - 2.0:
                    continue
                if any(not lo - 1.0 <= pts[k].x <= hi + 1.0 for k in inner):
                    continue
                if best is None or len(chain) < len(best):
                    best = chain
        if best is not None:
            pts = _replace_chain(pts, best, [])
    return pts


def _two_feet(points: list[Vec2]) -> tuple[int, int] | None:
    """いちばん下の点と、そこから横に離れた次に低い点。"""
    ordered = sorted(range(len(points)), key=lambda i: points[i].y)
    first = ordered[0]
    for index in ordered[1:]:
        if abs(points[index].x - points[first].x) > 20.0:
            return first, index
    return None


def bevel_apex_valley(points: list[Vec2]) -> list[Vec2]:
    """先端の谷と、左右で高さが違う切り口を、下端の直線に揃える。"""
    pts = _ring(points)
    if len(pts) < 6:
        return pts
    feet = _two_feet(pts)
    if feet is None:
        return pts
    left, right = feet
    if abs(pts[left].x - pts[right].x) < 8.0:
        return pts
    chains = [
        chain
        for chain in (_chain_through(pts, left, right, left), _chain_through(pts, right, left, right))
        if chain is not None and len(chain) <= 4
    ]
    if not chains:
        return pts
    chain = min(chains, key=len)
    floor = max(pts[chain[0]].y, pts[chain[-1]].y)
    peaks = [index for index in chain[1:-1] if pts[index].y > floor + 6.0]
    dips = [index for index in chain if pts[index].y < floor - 3.0]
    if not peaks and not dips:
        return pts
    out = list(pts)
    for index in dips:
        out[index] = Vec2(out[index].x, floor)
    if peaks and len(peaks) == len(chain) - 2:
        return _replace_chain(out, chain, [])
    return out


def _segment_angle(start: Vec2, end: Vec2) -> float | None:
    delta = end - start
    if delta.length() < 14.0:
        return None
    return math.atan2(delta.y, delta.x)


def _angle_spread(angles: list[float]) -> float:
    base = angles[0]
    deltas = [((angle - base + math.pi) % (2.0 * math.pi)) - math.pi for angle in angles]
    return max(deltas) - min(deltas)


def _bottom_run(points: list[Vec2]) -> tuple[int, int] | None:
    """下端で横に続く点の列。底が二箇所ある字は対象外。"""
    n = len(points)
    ymin = min(point.y for point in points)
    seen = [False] * n
    runs: list[tuple[int, int]] = []
    for index in range(n):
        if seen[index] or points[index].y > ymin + 2.5:
            continue
        start = index
        while points[(start - 1) % n].y <= ymin + 2.5:
            start = (start - 1) % n
            if start == index:
                return None
        end = index
        while points[(end + 1) % n].y <= ymin + 2.5:
            end = (end + 1) % n
            if end == start:
                return None
        cursor = start
        count = 0
        while True:
            seen[cursor] = True
            count += 1
            if cursor == end:
                break
            cursor = (cursor + 1) % n
            if count > n:
                return None
        runs.append((start, end))
    if len(runs) != 1:
        return None
    start, end = runs[0]
    if abs(points[end].x - points[start].x) < 36.0:
        return None
    # 丸い底（O やポップの先端）は水平に潰さない。
    index = (start + 1) % n
    guard = 0
    while index != end and guard < n:
        if _chord_depth(points[index], points[start], points[end]) > 2.0:
            return None
        index = (index + 1) % n
        guard += 1
    # 抜け際が水平に近いのは丸い底。V の外縁はすぐに立つ。
    before = points[(start - 1) % n]
    after = points[(end + 1) % n]

    def steep(here: Vec2, nxt: Vec2) -> bool:
        return abs(nxt.y - here.y) > abs(nxt.x - here.x) * 1.15

    if not steep(points[start], before) or not steep(points[end], after):
        return None
    return start, end


def _flatten_run(points: list[Vec2], start: int, end: int) -> list[Vec2]:
    floor = max(points[start].y, points[end].y)
    out = list(points)
    index = start
    guard = 0
    while True:
        if out[index].y != floor:
            out[index] = Vec2(out[index].x, floor)
        if index == end:
            break
        index = (index + 1) % len(out)
        guard += 1
        if guard > len(out):
            return points
    return out


def _stable_index(points: list[Vec2], start: int, step: int, limit_y: float, *, outward_x: float) -> int | None:
    """先端から離れた外縁。外へ開く向きだけを外縁とみなす。"""
    n = len(points)
    for hop in range(1, 12):
        origin = (start + step * hop) % n
        if points[origin].y > limit_y:
            return None
        angles: list[float] = []
        aligned = True
        for jump in range(3):
            first = (origin + step * jump) % n
            second = (origin + step * (jump + 1)) % n
            if step > 0:
                angle = _segment_angle(points[first], points[second])
            else:
                angle = _segment_angle(points[second], points[first])
            if angle is None or points[second].y > limit_y + 80.0:
                aligned = False
                break
            angles.append(angle)
        if not aligned or _angle_spread(angles) >= math.radians(8.0):
            continue
        # 右の外縁は上へ行くほど右、左の外縁は上へ行くほど左。
        if math.cos(angles[0]) * outward_x <= 0.15 or math.sin(angles[0]) <= 0.25:
            continue
        return origin
    return None


def _drop_between(points: list[Vec2], start: int, end: int, step: int) -> list[Vec2]:
    n = len(points)
    middle: list[int] = []
    index = (start + step) % n
    guard = 0
    while index != end and guard < n:
        middle.append(index)
        index = (index + step) % n
        guard += 1
    if not middle or guard >= n:
        return points
    if max(_chord_depth(points[index], points[start], points[end]) for index in middle) < 6.0:
        return points
    if step > 0:
        chain = [start, *middle, end]
    else:
        chain = [end, *reversed(middle), start]
    return _replace_chain(points, chain, [])


def trim_apex_stub(points: list[Vec2]) -> list[Vec2]:
    """先端の水平切り口から、細い画の端が横にはみ出した分を外縁まで落とす。"""
    pts = _ring(points)
    if len(pts) < 8:
        return pts
    for _ in range(2):
        run = _bottom_run(pts)
        if run is None:
            return pts
        flat, end = run
        pts = _flatten_run(pts, flat, end)
        ymin = min(point.y for point in pts)
        if pts[flat].x <= pts[end].x:
            sides = ((flat, -1, -1.0), (end, 1, 1.0))
        else:
            sides = ((end, 1, -1.0), (flat, -1, 1.0))
        changed = False
        for start, step, outward_x in sides:
            stable = _stable_index(pts, start, step, ymin + 220.0, outward_x=outward_x)
            if stable is None or pts[stable].y < pts[start].y + 15.0:
                continue
            updated = _drop_between(pts, start, stable, step)
            if updated is not pts and len(updated) != len(pts):
                pts = updated
                changed = True
                break
        if not changed:
            break
    return pts
