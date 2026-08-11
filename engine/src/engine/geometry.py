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


def parse_cubic_chain(points: Sequence[Vec2]) -> list[tuple[Vec2, Vec2, Vec2, Vec2]]:
    """連結 cubic 列。点数は 3n+1（n≥1）。"""
    pts = list(points)
    if len(pts) < 4 or (len(pts) - 1) % 3 != 0:
        raise ValueError(
            f"cubic chain needs 3n+1 points (got {len(pts)}); "
            "e.g. 4 for one cubic, 7 for two"
        )
    segs: list[tuple[Vec2, Vec2, Vec2, Vec2]] = []
    for i in range(0, len(pts) - 1, 3):
        segs.append((pts[i], pts[i + 1], pts[i + 2], pts[i + 3]))
    return segs


def sample_cubic_chain(
    points: Sequence[Vec2],
    n_per_seg: int = 48,
) -> list[tuple[Vec2, Vec2]]:
    """連結 cubic をセグメントごと等間隔 t でサンプル。接合点の重複を除く。"""
    segs = parse_cubic_chain(points)
    out: list[tuple[Vec2, Vec2]] = []
    for si, (p0, p1, p2, p3) in enumerate(segs):
        samples = sample_cubic(p0, p1, p2, p3, n=n_per_seg)
        if si > 0 and samples:
            samples = samples[1:]
        out.extend(samples)
    return out


def cumulative_arclength(samples: Sequence[tuple[Vec2, Vec2]]) -> list[float]:
    """各サンプルまでの累積弧長（先頭 0）。"""
    if not samples:
        return []
    acc = [0.0]
    for i in range(1, len(samples)):
        acc.append(acc[-1] + (samples[i][0] - samples[i - 1][0]).length())
    return acc


def resample_by_arclength(
    samples: Sequence[tuple[Vec2, Vec2]],
    n: int = 64,
) -> list[tuple[Vec2, Vec2, float]]:
    """弧長一様に再サンプルし (位置, 接線, s∈[0,1]) を返す。"""
    if len(samples) < 2:
        raise ValueError("need ≥2 samples for arclength resample")
    if n < 2:
        raise ValueError("n must be ≥2")
    cum = cumulative_arclength(samples)
    total = cum[-1]
    if total < 1e-9:
        pos, tan = samples[0]
        return [(pos, tan, 0.0)] * n
    out: list[tuple[Vec2, Vec2, float]] = []
    j = 0
    for i in range(n):
        target = (total * i) / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j]
        u = 0.0 if span < 1e-12 else (target - cum[j]) / span
        p0, t0 = samples[j]
        p1, t1 = samples[j + 1]
        pos = p0.lerp(p1, u)
        tan = (t0 * (1.0 - u) + t1 * u).normalized()
        if tan.length() < 1e-9:
            tan = (p1 - p0).normalized()
        out.append((pos, tan, target / total))
    return out


def interpolate_width_keys(
    s: float,
    keys: Sequence[tuple[float, float]],
) -> float:
    """弧長 s∈[0,1] の半幅を keyframe から区分線形補間（非単調可）。"""
    if not keys:
        raise ValueError("width keys empty")
    ordered = sorted((float(a), float(b)) for a, b in keys)
    if s <= ordered[0][0]:
        return ordered[0][1]
    if s >= ordered[-1][0]:
        return ordered[-1][1]
    for i in range(len(ordered) - 1):
        s0, w0 = ordered[i]
        s1, w1 = ordered[i + 1]
        if s0 <= s <= s1:
            if abs(s1 - s0) < 1e-12:
                return w1
            u = (s - s0) / (s1 - s0)
            return w0 + (w1 - w0) * u
    return ordered[-1][1]


def curvature_radii(
    samples: Sequence[tuple[Vec2, Vec2]],
) -> list[float]:
    """各内点の離散曲率半径。端点は +inf。長さは samples と同じ。"""
    n = len(samples)
    if n == 0:
        return []
    out = [float("inf")] * n
    if n < 3:
        return out
    pts = [s[0] for s in samples]
    for i in range(1, n - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ab = b - a
        bc = c - b
        lab = ab.length()
        lbc = bc.length()
        if lab < 1e-9 or lbc < 1e-9:
            continue
        cross = abs(ab.cross(bc))
        sin_theta = min(1.0, cross / (lab * lbc))
        theta = math.asin(sin_theta)
        chord = (c - a).length() * 0.5
        if theta < 1e-8 or chord < 1e-9:
            continue
        out[i] = chord / max(theta, 1e-8)
    return out


def min_curvature_radius(
    samples: Sequence[tuple[Vec2, Vec2]],
) -> float:
    """離散曲率から最小曲率半径を推定。退化時は +inf。"""
    radii = curvature_radii(samples)
    if not radii:
        return float("inf")
    return min(radii)


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
