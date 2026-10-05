"""高コントラストの碗。外形と穴を、ペンの進みに沿った曲がりで描く。

ペンでなぞった中心線を内側へ押し込むと、幅の変化が穴の曲がりを打ち消す。
山は半円にしない。接線がペンの細い方向を向くとき曲がりを強め、太い方向では開く。
平らな横画からその曲がりへは、曲率を上げながら入る。
"""

from __future__ import annotations

import math
from itertools import pairwise

from engine.geometry import Vec2

_FLAT_PAST_STEM = 42.0


def contrast_polygon(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    *,
    bar_half: float,
    theta_deg: float,
    facing_start: bool,
) -> list[Vec2]:
    """碗の塗り。widths はペンの半幅。facing_start の端は、向かいの碗と重なって横棒1本になる。"""
    if len(samples) < 4:
        return []
    outers, inners, tangents = _edges(samples, widths, bar_half, facing_start)
    angles = _angles(tangents)
    extreme = min(range(len(angles)), key=lambda i: abs(angles[i] - math.pi / 2.0))
    x_out = outers[extreme].x
    x_left = outers[0].x
    clear = x_left + max(widths) + _FLAT_PAST_STEM
    gap_low, gap_high = _side_gaps(angles, widths, theta_deg)
    x_low = x_out - gap_low
    x_high = x_out - gap_high
    inner = _pen_bow(x_left, inners[0].y, inners[-1].y, x_high, math.radians(theta_deg), clear)
    if not inner:
        inner_radius = _inner_radius(inners[0].y, inners[-1].y, x_low, x_high, clear)
        inner = _side(x_left, inners[0].y, inners[-1].y, x_low, x_high, inner_radius)
    # 外形は穴の外へ、その場所の画の太さだけ置く。穴の円弧より外形の円弧が
    # 遅いと、肩で画がステムより太くなる。
    outer = _offset_out(
        inner,
        inners[0].y - outers[0].y,
        outers[-1].y - inners[-1].y,
        gap_low,
        gap_high,
        outers[0].y,
        outers[-1].y,
    )
    return _clean(outer + list(reversed(inner)))


def _edges(samples, widths, bar_half, facing_start):
    positions = [pos for pos, _tangent in samples]
    tangents = [tangent for _pos, tangent in samples]
    area = sum(
        positions[i].x * positions[i + 1].y - positions[i + 1].x * positions[i].y
        for i in range(len(positions) - 1)
    )
    area += positions[-1].x * positions[0].y - positions[0].x * positions[-1].y
    outward_sign = -1.0 if area > 0.0 else 1.0
    thinnest = min(widths)
    level = [abs(tangent.y) <= abs(tangent.x) * 0.08 for tangent in tangents]
    reduced = _facing_run(level, facing_start)
    outers: list[Vec2] = []
    inners: list[Vec2] = []
    for index, ((pos, tangent), half) in enumerate(zip(samples, widths)):
        unit = tangent.normalized()
        if unit.length() < 1e-9:
            unit = Vec2(1.0, 0.0)
        outward = Vec2(-unit.y, unit.x) * outward_sign
        full = max(2.0 * half, 2.0 * bar_half) if level[index] else 2.0 * half
        if index in reduced:
            full = full / 2.0 + thinnest
        outer = pos + outward * thinnest
        outers.append(outer)
        inners.append(outer - outward * full)
    return outers, inners, tangents


def _facing_run(level: list[bool], facing_start: bool) -> set[int]:
    if facing_start:
        end = 0
        while end < len(level) - 1 and level[end]:
            end += 1
        return set(range(end + 1))
    start = len(level) - 1
    while start > 0 and level[start]:
        start -= 1
    return set(range(start, len(level)))


def _angles(tangents: list[Vec2]) -> list[float]:
    found: list[float] = []
    previous = 0.0
    for tangent in tangents:
        angle = math.atan2(tangent.y, tangent.x)
        if found:
            while angle < previous - math.pi:
                angle += 2.0 * math.pi
            while angle > previous + math.pi:
                angle -= 2.0 * math.pi
        found.append(angle)
        previous = angle
    return found


def _full_at(angles: list[float], widths: list[float], target: float) -> float:
    index = min(range(len(angles)), key=lambda i: abs(angles[i] - target))
    return 2.0 * widths[index]


def _side_gaps(angles: list[float], widths: list[float], theta_deg: float) -> tuple[float, float]:
    """右側の下端と上端の空き。太い方向が真横なら、右側はステム幅でまっすぐ。"""
    thick = math.radians(theta_deg) + math.pi / 2.0
    while thick > math.pi:
        thick -= math.pi
    stem = max(_full_at(angles, widths, thick), _full_at(angles, widths, math.pi / 2.0))
    # 太い方向が真横より上なら、右側の下を細くして右上が太く読めるようにする。
    # 1.03 は、碗を重ねたあと測る太さが、置いた空きより少し細くなる分。
    if _full_at(angles, widths, thick) > _full_at(angles, widths, math.pi / 2.0) * 1.03:
        return stem * 0.896, stem * 1.03
    return stem, stem


def _inner_radius(y0: float, y1: float, x_low: float, x_high: float, clear: float) -> float:
    """平らな辺が幹の右へ残る範囲で、一番大きい半径。

    上端を下げて斜めにするとき、半径を取りすぎると側辺が消えて円弧が外へはみ出す。
    側辺の傾きは垂直から 35° までにする。
    """
    height = y1 - y0
    dx = x_high - x_low
    # 垂直から 35° まで。側辺の高さが横のずれ / tan(35°) より短いと、それより寝る。
    min_span = abs(dx) / math.tan(math.radians(35.0)) if dx < -0.5 else 2.0
    radius = min(height / 2.0 - min_span / 2.0, max(8.0, x_low - clear))
    for _ in range(8):
        span = height - 2.0 * radius
        heading = math.atan2(max(span, 1.0), dx if abs(dx) > 0.01 else 0.0)
        if heading <= 0.15:
            heading = math.pi / 2.0
        limit = (x_low - clear) / max(math.sin(heading), 0.35)
        radius = min(height / 2.0 - min_span / 2.0, max(8.0, limit))
    return radius


def _pen_shape(theta: float, thin: float) -> float:
    """1 が基準。細い方向で大きく、太い方向で小さく、平らな端では弱くする。"""
    pen = 1.0 + 0.22 * math.cos(2.0 * (theta - thin))
    ease = math.sin(min(max(theta, 0.0), math.pi)) ** 0.85
    return 0.22 + 0.78 * ease * max(pen, 0.35)


def _pen_bow(
    x_left: float,
    y0: float,
    y1: float,
    x_right: float,
    thin: float,
    clear: float,
) -> list[Vec2]:
    """下の横画から上の横画まで。曲がりはペンの細い方向で強く、太い方向で開く。"""
    height = y1 - y0
    if height < 8.0:
        return []
    steps = 160
    cursor = Vec2(0.0, 0.0)
    raw = [cursor]
    for index in range(steps):
        start = math.pi * index / steps
        end = math.pi * (index + 1) / steps
        mid = (start + end) / 2.0
        step = Vec2(math.cos(mid), math.sin(mid)) * ((end - start) / _pen_shape(mid, thin))
        cursor = cursor + step
        raw.append(cursor)
    if raw[-1].y < 1.0:
        return []
    scale = height / raw[-1].y
    placed = [Vec2(point.x * scale, y0 + point.y * scale) for point in raw]
    peak = max(placed, key=lambda point: point.x)
    shift = x_right - peak.x
    placed = [Vec2(point.x + shift, point.y) for point in placed]
    # 開いた側が幹へ入り込むときは、右端を保ったまま横だけ縮める。
    left_limit = max(x_left + 8.0, clear)
    leftmost = min(placed[0].x, placed[-1].x)
    if leftmost < left_limit:
        span = x_right - leftmost
        room = x_right - left_limit
        if span < 1.0 or room < 8.0:
            return []
        factor = room / span
        placed = [Vec2(x_right + (point.x - x_right) * factor, point.y) for point in placed]
    points = [Vec2(x_left, y0), Vec2(placed[0].x, y0)]
    points.extend(placed[1:])
    points.append(Vec2(x_left, y1))
    return points


def _side(x_left: float, y0: float, y1: float, x_low: float, x_high: float, radius: float) -> list[Vec2]:
    """下の横画、円弧、右側、円弧、上の横画。向きは下から上。

    右側を斜めの直線にすると、その外側が平らに切れて山の曲線が折れる。
    直線が長くなるときは、天地を一つの円弧でつなぐ。
    """
    height = y1 - y0
    if x_high < x_low - 0.5 and height > 4.0:
        bow = height / 2.0
        start_x = x_high - bow
        if start_x > x_left + 8.0:
            points = [Vec2(x_left, y0), Vec2(start_x, y0)]
            points.extend(_arc(points[-1], 0.0, math.pi, bow))
            points.append(Vec2(x_left, y1))
            return points
    span = height - 2.0 * radius
    if span < 2.0:
        radius = (y1 - y0) / 2.0 - 1.0
        span = 2.0
    heading = math.atan2(span, x_high - x_low)
    if heading <= 0.15:
        heading = math.pi / 2.0
    y_low = y0 + radius * (1.0 - math.cos(heading))
    y_high = y_low + span
    start_x = x_low - radius * math.sin(heading)
    points = [Vec2(x_left, y0), Vec2(start_x, y0)]
    points.extend(_arc(points[-1], 0.0, heading, radius))
    points.append(Vec2(x_high, y_high))
    points.extend(_arc(points[-1], heading, math.pi, radius))
    points.append(Vec2(x_left, y1))
    return points


def _offset_out(
    inner: list[Vec2],
    w_bottom: float,
    w_top: float,
    w_low: float,
    w_high: float,
    y_bottom: float,
    y_top: float,
) -> list[Vec2]:
    """穴の点を、進行方向の右へ画の太さだけ動かす。横画の y は外形の端にそろえる。"""
    headings = []
    for start, end in pairwise(inner):
        delta = end - start
        headings.append(math.atan2(delta.y, delta.x))
    headings.append(headings[-1])
    points = []
    for point, heading in zip(inner, headings):
        turn = heading
        if turn < 0.0:
            turn += 2.0 * math.pi
        width = _width_at(turn, w_bottom, w_top, w_low, w_high)
        outward = Vec2(math.sin(heading), -math.cos(heading))
        moved = point + outward * width
        if abs(turn) < 0.2 or abs(turn - 2.0 * math.pi) < 0.2:
            moved = Vec2(moved.x, y_bottom)
        elif abs(turn - math.pi) < 0.2:
            moved = Vec2(moved.x, y_top)
        # 円弧の外側が天地を越すと、基準線とキャップからはみ出す。
        moved = Vec2(moved.x, min(y_top, max(y_bottom, moved.y)))
        points.append(moved)
    return points


def _smooth(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _width_at(heading: float, w_bottom: float, w_top: float, w_low: float, w_high: float) -> float:
    """下の横画から右側、上の横画へ、太さを滑らかに変える。

    右側の下と上で太さが違うとき、短い区間で上げると山の曲がりがそこだけ強くなる。
    真横の手前 35° から、それまでの傾きを保ったまま太い側へ寄せる。
    """
    if heading <= 0.05:
        return w_bottom
    if heading >= math.pi - 0.05:
        return w_top
    side = math.pi / 2.0
    rise = math.radians(35.0) if abs(w_high - w_low) > 0.5 else 0.0
    if heading >= side:
        return w_high + (w_top - w_high) * _smooth((heading - side) / (math.pi - side))
    if rise == 0.0 or heading < side - rise:
        return w_bottom + (w_low - w_bottom) * _smooth(heading / side)
    start = side - rise
    opened = _smooth(start / side)
    width = w_bottom + (w_low - w_bottom) * opened
    slope_t = start / side
    slope = (w_low - w_bottom) * (6.0 * slope_t * (1.0 - slope_t)) / side
    u = (heading - start) / rise
    settle = (2.0 * u - 3.0) * u * u + 1.0
    carry = u * (u - 1.0) ** 2
    arrive = (3.0 - 2.0 * u) * u * u
    return settle * width + carry * slope * rise + arrive * w_high


def _arc(start: Vec2, heading0: float, heading1: float, radius: float) -> list[Vec2]:
    """反時計回りの円弧。始点は含めない。中心は進行方向の左。"""
    center = start + Vec2(-math.sin(heading0), math.cos(heading0)) * radius
    steps = max(6, int(abs(heading1 - heading0) * radius / 4.0))
    points = []
    for step in range(1, steps + 1):
        heading = heading0 + (heading1 - heading0) * step / steps
        points.append(center + Vec2(math.sin(heading), -math.cos(heading)) * radius)
    return points


def ease_outer_cusp(points: list[Vec2], *, turn_deg: float = -100.0, cut: float = 8.0) -> list[Vec2]:
    """外の谷の鋭い折れを短い面取りにする。

    深い埋め直しは谷を右へ押し、肩の画がステムより太くなる。
    折れを -100° より緩くすると、その埋め直しは動かない。
    """
    if len(points) < 6:
        return points
    pts = list(points)
    if abs(pts[0].x - pts[-1].x) < 1e-6 and abs(pts[0].y - pts[-1].y) < 1e-6:
        pts = pts[:-1]
    limit = math.radians(turn_deg)
    eased: list[Vec2] = []
    count = len(pts)
    for index, point in enumerate(pts):
        prev, nxt = pts[index - 1], pts[(index + 1) % count]
        turn = math.atan2(nxt.y - point.y, nxt.x - point.x) - math.atan2(point.y - prev.y, point.x - prev.x)
        turn = (turn + math.pi) % (2.0 * math.pi) - math.pi
        back, fore = prev - point, nxt - point
        if turn >= limit or back.length() < 1.0 or fore.length() < 1.0:
            eased.append(point)
            continue
        reach = min(cut, back.length() * 0.45, fore.length() * 0.45)
        eased.append(point + back.normalized() * reach)
        eased.append(point + fore.normalized() * reach)
    return eased


def _clean(points: list[Vec2]) -> list[Vec2]:
    """0.01 単位に丸める。生の浮動小数のままだと、重なりの演算が輪郭を落とす。"""
    rounded = [Vec2(round(point.x, 2), round(point.y, 2)) for point in points]
    kept = [rounded[0]]
    for point in rounded[1:]:
        if (point - kept[-1]).length() > 0.05:
            kept.append(point)
    if len(kept) > 1 and (kept[0] - kept[-1]).length() < 0.05:
        kept.pop()
    return kept
