"""ベジェ曲線のサンプリングと可変幅オフセット用の幾何ユーティリティ。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, s: float) -> "Vec2":
        return Vec2(self.x * s, self.y * s)

    def __truediv__(self, s: float) -> "Vec2":
        return Vec2(self.x / s, self.y / s)

    def __rmul__(self, s: float) -> "Vec2":
        return self.__mul__(s)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: "Vec2") -> float:
        return self.x * other.y - self.y * other.x

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        L = self.length()
        if L < 1e-9:
            return Vec2(0.0, 0.0)
        return self / L

    def perpendicular(self) -> "Vec2":
        """左向き法線（進行方向に対して）。"""
        return Vec2(-self.y, self.x)

    def rotated(self, deg: float) -> "Vec2":
        r = math.radians(deg)
        c, s = math.cos(r), math.sin(r)
        return Vec2(self.x * c - self.y * s, self.x * s + self.y * c)

    def lerp(self, other: "Vec2", t: float) -> "Vec2":
        return self + (other - self) * t

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


Point = Vec2


def cubic_bezier(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: float) -> Vec2:
    u = 1.0 - t
    return (
        (u * u * u) * p0
        + (3 * u * u * t) * p1
        + (3 * u * t * t) * p2
        + (t * t * t) * p3
    )


def cubic_bezier_deriv(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: float) -> Vec2:
    u = 1.0 - t
    return (
        3 * (u * u) * (p1 - p0)
        + 6 * u * t * (p2 - p1)
        + 3 * (t * t) * (p3 - p2)
    )


def sample_cubic(
    p0: Vec2,
    p1: Vec2,
    p2: Vec2,
    p3: Vec2,
    n: int = 48,
) -> List[Tuple[Vec2, Vec2]]:
    """等間隔 t で (位置, 単位接線) を返す。"""
    out: List[Tuple[Vec2, Vec2]] = []
    for i in range(n + 1):
        t = i / n
        pos = cubic_bezier(p0, p1, p2, p3, t)
        tan = cubic_bezier_deriv(p0, p1, p2, p3, t).normalized()
        if tan.length() < 1e-9:
            # 退化時は前後から推定
            t2 = min(1.0, t + 1.0 / n)
            tan = (cubic_bezier(p0, p1, p2, p3, t2) - pos).normalized()
        out.append((pos, tan))
    return out


def sample_polyline(points: Sequence[Vec2], n_per_seg: int = 16) -> List[Tuple[Vec2, Vec2]]:
    """折れ線を密にサンプリングして (位置, 単位接線) を返す。"""
    if len(points) < 2:
        return []
    out: List[Tuple[Vec2, Vec2]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        tan = (b - a).normalized()
        steps = n_per_seg if i < len(points) - 2 else n_per_seg
        for j in range(steps):
            t = j / steps
            out.append((a.lerp(b, t), tan))
    last_tan = (points[-1] - points[-2]).normalized()
    out.append((points[-1], last_tan))
    return out


def smooth_tangents(samples: List[Tuple[Vec2, Vec2]]) -> List[Tuple[Vec2, Vec2]]:
    """隣接差分で接線を再推定し、端点付近の不安定を抑える。"""
    if len(samples) < 2:
        return samples
    pts = [s[0] for s in samples]
    out: List[Tuple[Vec2, Vec2]] = []
    for i, p in enumerate(pts):
        if i == 0:
            tan = (pts[1] - pts[0]).normalized()
        elif i == len(pts) - 1:
            tan = (pts[-1] - pts[-2]).normalized()
        else:
            tan = (pts[i + 1] - pts[i - 1]).normalized()
        if tan.length() < 1e-9:
            tan = samples[i][1]
        out.append((p, tan))
    return out


def variable_width_outline(
    samples: Sequence[Tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
    close: bool = True,
) -> List[Vec2]:
    """
    中心線サンプルと半幅から左右オフセットし、閉じたポリゴンを返す。
    進行方向左側が left、右側が right。
    """
    assert len(samples) == len(half_widths)
    left: List[Vec2] = []
    right: List[Vec2] = []
    prev_n: Vec2 | None = None
    for (pos, tan), hw in zip(samples, half_widths):
        n = tan.perpendicular().normalized()
        if n.length() < 1e-9:
            n = prev_n if prev_n is not None else Vec2(0.0, -1.0)
        # 法線フリップ防止（急カーブで裏返らないように）
        if prev_n is not None and n.dot(prev_n) < 0:
            n = n * -1.0
        prev_n = n
        left.append(pos + n * hw)
        right.append(pos - n * hw)

    # 先端半幅が 0 に近い場合は左右が重なるので先端を1点にまとめる
    tip_hw = half_widths[-1]
    root_hw = half_widths[0]
    poly: List[Vec2] = []
    poly.extend(left)
    if tip_hw > 0.5:
        # 先端を半円風に接続（左右端点をそのまま繋ぐ）
        poly.extend(reversed(right))
    else:
        # 鋭い先端: 中心線先端を経由
        tip = samples[-1][0]
        poly.append(tip)
        poly.extend(reversed(right[:-1] if len(right) > 1 else right))

    if root_hw < 0.5 and len(poly) > 2:
        # 根元も尖らせる場合は先頭を中心に寄せる（通常は使わない）
        pass

    if close and poly and poly[0] != poly[-1]:
        poly.append(poly[0])
    return poly


def polygon_to_svg_path(points: Sequence[Vec2], precision: int = 2) -> str:
    if not points:
        return ""
    fmt = f"{{:.{precision}f}}"
    parts = [f"M {fmt.format(points[0].x)} {fmt.format(points[0].y)}"]
    for p in points[1:]:
        parts.append(f"L {fmt.format(p.x)} {fmt.format(p.y)}")
    if points[0].as_tuple() != points[-1].as_tuple():
        parts.append("Z")
    else:
        # 既に閉じている場合も Z を付けて明示
        parts.append("Z")
    return " ".join(parts)


def union_bbox(polys: Iterable[Sequence[Vec2]]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for poly in polys:
        for p in poly:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))
