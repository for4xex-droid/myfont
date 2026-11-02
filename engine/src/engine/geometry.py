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
from itertools import pairwise

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


def limit_half_to_curvature(
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
) -> list[float]:
    """半幅が局所の曲率半径を超える点は、半径まで落とす。

    端の曲率は隣の点を使う。半径を超えたペンは内周が折り返し、壁が棘になる。
    """
    radii = curvature_radii(samples)
    if len(radii) >= 3:
        radii[0] = radii[1]
        radii[-1] = radii[-2]
    return [
        min(width, radius)
        for width, radius in zip(half_widths, radii, strict=True)
    ]


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


def _offset_sides(
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
) -> tuple[list[Vec2], list[Vec2]]:
    """中心線サンプルから左右オフセット点列（未クローズ）。"""
    assert len(samples) == len(half_widths)
    left: list[Vec2] = []
    right: list[Vec2] = []
    prev_n: Vec2 | None = None
    for (pos, tan), hw in zip(samples, half_widths):
        n = tan.perpendicular().normalized()
        if n.length() < 1e-9:
            n = prev_n if prev_n is not None else Vec2(0.0, -1.0)
        if prev_n is not None and n.dot(prev_n) < 0:
            n = n * -1.0
        prev_n = n
        left.append(pos + n * hw)
        right.append(pos - n * hw)
    return left, right


def _poly_abs_area(poly: Sequence[Vec2]) -> float:
    pts = list(poly)
    if len(pts) >= 2 and pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i].x, pts[i].y
        x2, y2 = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        a += x1 * y2 - x2 * y1
    return abs(0.5 * a)


def _poly_signed_area(poly: Sequence[Vec2]) -> float:
    pts = list(poly)
    if len(pts) >= 2 and pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i].x, pts[i].y
        x2, y2 = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        a += x1 * y2 - x2 * y1
    return 0.5 * a


def _close_ring(pts: Sequence[Vec2]) -> list[Vec2]:
    out = list(pts)
    if len(out) >= 2 and out[0].as_tuple() == out[-1].as_tuple():
        out = out[:-1]
    if out and out[0].as_tuple() != out[-1].as_tuple():
        out.append(out[0])
    return out


# 右の極の直後で内周の曲率が跳ねる範囲。伸ばすと、置き換える五次が波打つ。
_FAIR_PAD = 20
_FAIR_REACH = 60
_INNER_JUMP = 6.0


def _poly_jump(points: Sequence[Vec2]) -> float:
    """右端の近くで、3 単位おきに測った曲率の跳び。開いた側の両端は結ばない。"""
    if len(points) < 8:
        return 0.0
    stepped = [points[0]]
    carry = 0.0
    for start, end in pairwise(points):
        length = (end - start).length()
        if length < 1e-9:
            continue
        cursor = 3.0 - carry
        while cursor <= length:
            stepped.append(start + (end - start) * (cursor / length))
            cursor += 3.0
        carry = length - (cursor - 3.0)
    count = len(stepped)
    if count < 8:
        return 0.0
    curve = [0.0] * count
    for index in range(2, count - 2):
        a, b, c = stepped[index - 2], stepped[index], stepped[index + 2]
        turn = math.atan2(c.y - b.y, c.x - b.x) - math.atan2(b.y - a.y, b.x - a.x)
        turn = (turn + math.pi) % (2.0 * math.pi) - math.pi
        curve[index] = math.degrees(turn) / 6.0 * 10.0
    right = max(point.x for point in stepped)
    worst = 0.0
    for index in range(2, count - 5):
        if stepped[index].x < right - 40.0:
            continue
        worst = max(worst, abs(curve[index + 3] - curve[index]))
    return worst


def _local_curvature(points: Sequence[Vec2], index: int) -> float:
    a, b, c = points[index - 2], points[index], points[index + 2]
    turn = math.atan2(c.y - b.y, c.x - b.x) - math.atan2(b.y - a.y, b.x - a.x)
    turn = (turn + math.pi) % (2.0 * math.pi) - math.pi
    length = (b - a).length() + (c - b).length()
    if length < 1e-9:
        return 0.0
    return abs(math.degrees(turn) / length * 10.0)


def _quintic(x0, s0, q0, x1, s1, q1) -> tuple[float, float, float, float, float, float]:
    """両端の位置・傾き・二階を通す五次。係数は u の 0 次から。"""
    a0 = x0
    a1 = s0
    a2 = q0 / 2.0
    remain = x1 - a0 - a1 - a2
    slope = s1 - a1 - 2.0 * a2
    curve = q1 - 2.0 * a2
    first = slope - 3.0 * remain
    second = curve - 6.0 * remain
    a5 = (second - 6.0 * first) / 2.0
    a4 = first - 2.0 * a5
    a3 = remain - a4 - a5
    return (a0, a1, a2, a3, a4, a5)


def fair_inner_right(
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
    left: list[Vec2],
) -> list[Vec2]:
    """右の極で内周が跳ねるとき、その前後を y に対する滑らかな x で置き換える。

    接線を固定した三次は、極の直後に曲率の山を作る。太いペンでは内周だけその山が跳ねる。
    中心線より外側の側、山が検査の帯（6）以内の側、置き換えると跳びが増える側は動かさない。
    窓の幅はサンプル数で、区間あたりのサンプル数を変えると山の取り方が変わる。
    """
    count = len(left)
    if count < _FAIR_PAD + _FAIR_REACH + 8 or len(samples) != len(half_widths):
        return left
    index = max(range(count), key=lambda i: left[i].x)
    if index < 4 or index > count - 6:
        return left
    center = max(range(len(samples)), key=lambda i: samples[i][0].x)
    half = half_widths[center]
    inward = samples[center][0].x - left[index].x
    if inward < half - 8.0 or inward > half + 8.0:
        return left
    jump = _poly_jump(left)
    if jump <= _INNER_JUMP:
        return left
    floor = _local_curvature(left, min(count - 3, index + _FAIR_PAD + _FAIR_REACH))
    stop = index
    while stop < count - 6 and _local_curvature(left, stop) > floor + 4.0:
        stop += 1
    start = max(3, index - _FAIR_PAD)
    stop = min(count - 4, stop + _FAIR_PAD)
    y0, y1 = left[start].y, left[stop].y
    span = y1 - y0
    if abs(span) < 1.0 or stop - start < 6:
        return left
    sign = 1.0 if span > 0.0 else -1.0
    if any((left[i + 1].y - left[i].y) * sign <= 0.0 for i in range(start, stop)):
        return left

    def spaced(i: int) -> bool:
        return (
            abs(left[i + 1].y - left[i].y) >= 0.05
            and abs(left[i].y - left[i - 1].y) >= 0.05
        )

    if not spaced(start) or not spaced(stop):
        return left

    def slope(i: int) -> float:
        return (left[i + 1].x - left[i - 1].x) / (left[i + 1].y - left[i - 1].y)

    def bend(i: int) -> float:
        forward = (left[i + 1].x - left[i].x) / (left[i + 1].y - left[i].y)
        back = (left[i].x - left[i - 1].x) / (left[i].y - left[i - 1].y)
        return (forward - back) / ((left[i + 1].y - left[i - 1].y) / 2.0)

    coef = _quintic(
        left[start].x,
        slope(start) * span,
        bend(start) * span * span,
        left[stop].x,
        slope(stop) * span,
        bend(stop) * span * span,
    )
    replaced = list(left)
    for i in range(start, stop + 1):
        u = (left[i].y - y0) / span
        value = 0.0
        for term in reversed(coef):
            value = value * u + term
        replaced[i] = Vec2(value, left[i].y)
    if _poly_jump(replaced) > jump:
        return left
    return replaced


def variable_width_outline(
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
    close: bool = True,
) -> list[Vec2]:
    """
    中心線サンプルと半幅から左右オフセットし、閉じたポリゴンを返す。
    進行方向左側が left、右側が right。
    """
    left, right = _offset_sides(samples, half_widths)
    left = fair_inner_right(samples, half_widths, left)

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


def variable_width_ring_outlines(
    samples: Sequence[tuple[Vec2, Vec2]],
    half_widths: Sequence[float],
) -> tuple[list[Vec2], list[Vec2]]:
    """閉じた中心線から outer / inner の2輪郭を返す（穴付きリング）。

    pathops union で穴を残すため、inner は outer と逆巻きにする。
    """
    if len(samples) < 3:
        raise ValueError("ring outline needs ≥3 samples")
    # 閉じサンプルの重複終点を落とす
    work = list(samples)
    hws = list(half_widths)
    if (
        len(work) >= 2
        and (work[0][0] - work[-1][0]).length() < 1e-6
    ):
        work = work[:-1]
        hws = hws[:-1]
    left, right = _offset_sides(work, hws)
    ring_a = _close_ring(left)
    ring_b = _close_ring(right)
    if _poly_abs_area(ring_a) >= _poly_abs_area(ring_b):
        outer, inner = ring_a, ring_b
    else:
        outer, inner = ring_b, ring_a
    # 同符号なら inner を反転（union で穴が潰れるのを防ぐ）
    if _poly_signed_area(outer) * _poly_signed_area(inner) > 0:
        inner = list(reversed(inner))
    return outer, inner


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
