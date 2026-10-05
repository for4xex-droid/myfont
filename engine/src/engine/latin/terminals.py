"""端物。ペンでは掃かず、閉じた塗り部品として返す。"""

from __future__ import annotations

import math

from engine.geometry import Vec2


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
    raise ValueError(f"unknown terminal {kind!r}")
