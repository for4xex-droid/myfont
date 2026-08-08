"""ベジェ曲線のサンプリングと可変幅オフセット用の幾何ユーティリティ。

座標方針（GOLDENRULES 掟1）:
  目標はフォント空間（Y上・UPM=1000）。
  現行 engine の骨格・肉付けは prototype 由来の SVG Y下（legacy）のまま。
  UFO/OTF 書き出し前に必ず to_font_y() で変換すること（T7 ゲート）。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

UPM = 1000

# "svg_y_down_legacy" | "font_y_up"
# font_y_up への切替は骨格Y変換＋strokes 符号の同時移行が必須（単独切替禁止）。
_ALLOWED_COORDINATE_SPACES = frozenset({"svg_y_down_legacy", "font_y_up"})
COORDINATE_SPACE = "svg_y_down_legacy"
if COORDINATE_SPACE not in _ALLOWED_COORDINATE_SPACES:
    raise RuntimeError(f"invalid COORDINATE_SPACE: {COORDINATE_SPACE!r}")


def to_svg_y(y_font: float, upm: int = UPM) -> float:
    """フォント空間 Y → SVG Y（下向き）。"""
    return upm - y_font


def to_font_y(y_svg: float, upm: int = UPM) -> float:
    """SVG Y → フォント空間 Y。legacy 内部座標から UFO へ書くときに使う。"""
    return upm - y_svg


def y_for_svg(y_internal: float, upm: int = UPM) -> float:
    """内部座標 → SVG 描画用 Y。"""
    if COORDINATE_SPACE == "svg_y_down_legacy":
        return y_internal
    return to_svg_y(y_internal, upm)


def y_for_font(y_internal: float, upm: int = UPM) -> float:
    """内部座標 → フォント空間 Y（UFO 用）。"""
    if COORDINATE_SPACE == "svg_y_down_legacy":
        return to_font_y(y_internal, upm)
    return y_internal


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, s: float) -> Vec2:
        return Vec2(self.x * s, self.y * s)

    def __truediv__(self, s: float) -> Vec2:
        return Vec2(self.x / s, self.y / s)

    def __rmul__(self, s: float) -> Vec2:
        return self.__mul__(s)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vec2) -> float:
        return self.x * other.y - self.y * other.x

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vec2:
        L = self.length()
        if L < 1e-9:
            return Vec2(0.0, 0.0)
        return self / L

    def perpendicular(self) -> Vec2:
        """左向き法線（進行方向に対して）。"""
        return Vec2(-self.y, self.x)

    def rotated(self, deg: float) -> Vec2:
        r = math.radians(deg)
        c, s = math.cos(r), math.sin(r)
        return Vec2(self.x * c - self.y * s, self.x * s + self.y * c)

    def lerp(self, other: Vec2, t: float) -> Vec2:
        return self + (other - self) * t

    def as_tuple(self) -> tuple[float, float]:
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
) -> list[tuple[Vec2, Vec2]]:
    """等間隔 t で (位置, 単位接線) を返す。"""
    out: list[tuple[Vec2, Vec2]] = []
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


def sample_polyline(points: Sequence[Vec2], n_per_seg: int = 16) -> list[tuple[Vec2, Vec2]]:
    """折れ線を密にサンプリングして (位置, 単位接線) を返す。"""
    if len(points) < 2:
        return []
    out: list[tuple[Vec2, Vec2]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        tan = (b - a).normalized()
        for j in range(n_per_seg):
            t = j / n_per_seg
            out.append((a.lerp(b, t), tan))
    last_tan = (points[-1] - points[-2]).normalized()
    out.append((points[-1], last_tan))
    return out


def smooth_tangents(samples: list[tuple[Vec2, Vec2]]) -> list[tuple[Vec2, Vec2]]:
    """隣接差分で接線を再推定し、端点付近の不安定を抑える。"""
    if len(samples) < 2:
        return samples
    pts = [s[0] for s in samples]
    out: list[tuple[Vec2, Vec2]] = []
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
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
    close: bool = True,
) -> list[Vec2]:
    """
    中心線サンプルと半幅から左右オフセットし、閉じたポリゴンを返す。
    進行方向左側が left、右側が right。
    """
    assert len(samples) == len(half_widths)
    left: list[Vec2] = []
    right: list[Vec2] = []
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
    poly: list[Vec2] = []
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
    """内部座標ポリゴンを SVG path d へ（COORDINATE_SPACE に応じ Y 変換）。"""
    if not points:
        return ""
    fmt = f"{{:.{precision}f}}"
    parts = [
        f"M {fmt.format(points[0].x)} {fmt.format(y_for_svg(points[0].y))}"
    ]
    for pt in points[1:]:
        parts.append(f"L {fmt.format(pt.x)} {fmt.format(y_for_svg(pt.y))}")
    parts.append("Z")
    return " ".join(parts)


def union_bbox(
    polys: Iterable[Sequence[Vec2]],
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for poly in polys:
        for p in poly:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))
