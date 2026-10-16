"""端物。ペンでは掃かず、閉じた塗り部品として返す。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from engine.geometry import Vec2, _offset_sides


def _semicircle(origin: Vec2, outward: Vec2, radius: float, steps: int = 16) -> list[Vec2]:
    normal = outward.perpendicular().normalized()
    direction = outward.normalized()
    points: list[Vec2] = []
    for i in range(steps + 1):
        angle = -math.pi / 2.0 + math.pi * i / steps
        points.append(origin + direction * (radius * math.cos(angle)) + normal * (radius * math.sin(angle)))
    return points


def _slab(origin: Vec2, outward: Vec2, length: float, thick: float) -> list[Vec2]:
    """幹の端に内側から載せる横棒。外の面は幹の端と同じ高さ。"""
    direction = outward.normalized()
    normal = direction.perpendicular()
    back = origin - direction * (thick * 1.35)
    front = origin
    half = length / 2.0
    return [
        back + normal * half,
        front + normal * half,
        front - normal * half,
        back - normal * half,
    ]


def _bracket(origin: Vec2, outward: Vec2, length: float, thick: float, bracket: float, half_width: float) -> list[Vec2]:
    """セリフの横棒と、幹へ戻る短いブラケット。自己交差しない六角形。"""
    direction = outward.normalized()
    normal = direction.perpendicular()
    back = origin - direction * (thick * 1.35)
    front = origin
    half = length / 2.0
    neck = min(half * 0.55, max(half_width, 1.0))
    inner = origin - direction * (thick * 1.35 + max(bracket, thick))
    return [
        front + normal * half,
        front - normal * half,
        back - normal * half,
        inner - normal * neck,
        inner + normal * neck,
        back + normal * half,
    ]


def _quad(start: Vec2, control: Vec2, end: Vec2, steps: int) -> list[Vec2]:
    points: list[Vec2] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        points.append(start * (u * u) + control * (2.0 * u * t) + end * (t * t))
    return points


@dataclass(frozen=True)
class Beak:
    """くちばしの寸法（UPM）。sweep が正ならシックのつなぎ、0 ならクラシックの板とブラケット。"""

    drop: float
    thick: float
    bracket: float = 0.0
    sweep: float = 0.0
    tip: float = 0.0


# シックのつなぎの3次曲線の取っ手。始点側はつなぎの長さ、終点側は縦の落ちに掛ける。
_SWEEP_PULL = (0.75, 0.4)


def _cubic(a: Vec2, b: Vec2, c: Vec2, d: Vec2, t: float) -> Vec2:
    u = 1.0 - t
    return a * (u * u * u) + b * (3.0 * u * u * t) + c * (3.0 * u * t * t) + d * (t * t * t)


def _cross_x(points: list[Vec2], x: float) -> tuple[Vec2, int] | None:
    """点列が縦の線 x を初めて横切る位置と、その辺の始点の番号。"""
    for i, (a, b) in enumerate(pairwise(points)):
        if (a.x - x) * (b.x - x) <= 0.0 and abs(b.x - a.x) > 1e-9:
            return a + (b - a) * ((x - a.x) / (b.x - a.x)), i
    return None


def _walk(points: list[Vec2], start: Vec2, index: int, distance: float) -> tuple[Vec2, int]:
    """points[index] と points[index + 1] の間の start から、先へ distance 進む。
    戻り値の番号は、着いた点の次の点。"""
    left = distance
    here = start
    i = index + 1
    while i < len(points):
        step = (points[i] - here).length()
        if step >= left and step > 1e-9:
            return here + (points[i] - here) * (left / step), i
        left -= step
        here = points[i]
        i += 1
    return points[-1], len(points) - 1


def _sweep_handle(
    path: list[Vec2], meet: Vec2, meet_index: int, back: Vec2, c2: Vec2, chord: float, sweep: float
) -> float:
    """つなぎの始点の取っ手の長さ。内縁の曲がり κ に合わせる（κ0 = (2/3)·h / a²）。"""
    ahead, _ = _walk(path, meet, meet_index - 1, 8.0)
    behind = path[max(1, meet_index - 1)]
    for j in range(meet_index - 1, 0, -1):
        if (path[j] - meet).length() >= 8.0:
            behind = path[j]
            break
    u1 = (meet - ahead).normalized()
    u2 = (behind - meet).normalized()
    span = ((meet - ahead).length() + (behind - meet).length()) / 2.0
    kappa = abs(u1.cross(u2)) / max(span, 1e-6)
    h = abs(back.cross(c2 - meet))
    if kappa <= 1e-6:
        return _SWEEP_PULL[0] * sweep
    return max(0.15 * chord, min(0.95 * chord, math.sqrt(2.0 * h / (3.0 * kappa))))


def _beak(
    origin: Vec2,
    outward: Vec2,
    half_width: float,
    beak: Beak,
    samples: list[tuple[Vec2, Vec2]] | None = None,
    widths: list[float] | None = None,
    index: int | None = None,
) -> list[Vec2]:
    """腕の端から字の内側へ垂らすくちばし。外の面は端の外側の角を通る縦の線、上端は腕の外縁。

    クラシックは厚さ thick の縦の板で、内の面と腕の内縁を白地側の凹曲線（bracket）でつなぐ。
    シックは内の面を3次曲線にし、腕の内縁を端から sweep 戻った点で、接線と曲がりを合わせて入る。
    """
    normal = outward.normalized().perpendicular()
    a, b = origin + normal * half_width, origin - normal * half_width
    if samples:
        ys = [pos.y for pos, _tangent in samples]
        top = origin.y > (min(ys) + max(ys)) / 2.0
    else:
        top = True
    outer, inner = (a, b) if (a.y > b.y) == top else (b, a)
    sx = 1.0 if outward.x > 0.0 else -1.0
    v = -1.0 if top else 1.0
    xf = max(outer.x, inner.x) if sx > 0.0 else min(outer.x, inner.x)
    tip_y = outer.y + v * beak.drop
    if samples is None or widths is None or index is None:
        face_x = xf - sx * max(beak.thick, 1.0)
        return [outer, Vec2(xf, outer.y), Vec2(xf, tip_y), Vec2(face_x, tip_y), Vec2(face_x, inner.y), inner]
    left, right = _offset_sides(samples, widths)
    side = left if (left[index] - inner).length() < (right[index] - inner).length() else right
    edge = side if index == 0 else list(reversed(side))
    path = [outer, inner, *edge[1:]]
    if beak.sweep > 0.0:
        tip = Vec2(xf - sx * beak.tip, tip_y)
        meet, meet_index = _walk(path, path[1], 1, beak.sweep)
        back = path[meet_index - 1] - meet
        if back.length() < 1e-6:
            back = path[meet_index - 1] - path[meet_index]
        back = back.normalized()
        c2 = tip - Vec2(0.0, v) * (abs(tip_y - meet.y) * _SWEEP_PULL[1])
        reach = _sweep_handle(path, meet, meet_index, back, c2, (tip - meet).length(), beak.sweep)
        c1 = meet + back * reach
        curve = [_cubic(meet, c1, c2, tip, k / 32) for k in range(33)]
        head = [outer, Vec2(xf, outer.y), Vec2(xf, tip_y), tip]
        tail = list(reversed(path[1:meet_index])) if meet_index > 1 else []
        return head + list(reversed(curve))[1:] + tail
    face_x = xf - sx * max(beak.thick, 1.0)
    head = [outer, Vec2(xf, outer.y), Vec2(xf, tip_y), Vec2(face_x, tip_y)]
    # 交点は「外の角 → 内の角 → 内縁」の一続きで探す。内縁だけだと、傾いた切り口を越えて遠くの背に当たる。
    found = _cross_x(path, face_x)
    if found is None:
        return [*head, Vec2(face_x, inner.y), inner]
    hit, hit_index = found
    face = abs(tip_y - hit.y)
    if beak.bracket > 1.0 and face > beak.bracket + 4.0:
        shoulder = Vec2(face_x, hit.y + v * beak.bracket)
        meet, meet_index = _walk(path, hit, hit_index, beak.bracket)
        body = [shoulder, *_quad(shoulder, hit, meet, 24)[1:]]
    else:
        meet_index = hit_index
        body = [hit]
    return head + body + list(reversed(path[1 : meet_index + 1]))


def terminal_polygon(
    kind: str,
    origin: Vec2,
    outward: Vec2,
    half_width: float,
    *,
    serif_length: float,
    serif_thick: float,
    round_frac: float,
    bracket: float,
    samples: list[tuple[Vec2, Vec2]] | None = None,
    widths: list[float] | None = None,
    index: int | None = None,
    beak: Beak | None = None,
) -> list[Vec2] | None:
    """テンプレ1個。平坦な端と頂点は None（幹の切り口のまま）。"""
    if kind in ("flat", "none", "apex_sharp", "apex_cut"):
        return None
    if outward.length() < 1e-9 or half_width <= 0.0:
        return None
    if kind == "round":
        # 端の半径は幹の半幅。角の丸め率はボール端にだけ足す。
        extra = half_width * max(0.0, round_frac - 1.0)
        return _semicircle(origin, outward, half_width + extra)
    if kind == "ball":
        return _semicircle(origin, outward, half_width * 1.15)
    if kind == "serif_hairline":
        return _slab(origin, outward, serif_length, max(serif_thick, 1.0))
    if kind == "serif_bracketed":
        return _bracket(origin, outward, serif_length, max(serif_thick, 1.0), bracket, half_width)
    if kind == "spur":
        return _slab(origin, outward, serif_length * 0.45, max(serif_thick, 1.0))
    if kind == "beak":
        if beak is None:
            raise ValueError("beak: dimensions required")
        return _beak(origin, outward, half_width, beak, samples, widths, index)
    raise ValueError(f"unknown terminal {kind!r}")
