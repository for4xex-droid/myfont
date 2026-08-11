"""骨格＋端点タグから明朝体ディテール付きアウトラインを生成する。"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from engine.geometry import (
    Vec2,
    curvature_radii,
    interpolate_width_keys,
    parse_cubic_chain,
    polygon_to_svg_path,
    resample_by_arclength,
    sample_cubic,
    sample_cubic_chain,
    sample_polyline,
    smooth_tangents,
    variable_width_outline,
)
from engine.params import MinchoParams

# 仮名肉付け前ゲート: 局所曲率半径 ≥ この係数 × 局所半幅（違反は YAML 側 fail）
# 離散曲率は過大推定しがちなので 1.0 厳格にはしない（自己交差の実害が出る帯で止める）
KANA_CURVATURE_RADIUS_FACTOR = 0.55
# 弧長一様サンプル数（仮名）
KANA_ARCLENGTH_SAMPLES = 72
# cubic 節点上限（制御点込みの点数 = 3n+1 ≤ この値 → n≤6 なら 19）
KANA_MAX_SPINE_POINTS = 19


class StrokeKind(str, Enum):
    HORIZONTAL = "horizontal"  # 横画
    VERTICAL = "vertical"  # 縦画
    LEFT_HARA = "left_hara"  # 左はらい（撇）
    RIGHT_HARA = "right_hara"  # 右はらい（捺）
    TEN = "ten"  # 点
    KANA_CURVE = "kana_curve"  # 仮名パラメトリック曲線（P1-B）


class EndTag(str, Enum):
    NONE = "none"
    UROKO = "uroko"  # うろこ
    UCHIKOMI = "uchikomi"  # 打ち込み
    TOME = "tome"  # 止め
    HANE = "hane"  # はね
    TAPER = "taper"  # 先細り
    FLAT = "flat"


@dataclass
class SkeletonStroke:
    """1本の骨格ストローク。"""

    kind: StrokeKind
    # 直線なら [start, end]、曲線なら [p0, p1, p2, p3]（3次ベジェ）
    # KANA_CURVE は連結 cubic（3n+1 点）
    points: Sequence[Vec2]
    start_tag: EndTag = EndTag.NONE
    end_tag: EndTag = EndTag.NONE
    # 任意の上書き太さ（None なら params 既定）
    thickness: float | None = None
    # KANA_CURVE: 弧長 s∈[0,1] → 半幅 UPM（非単調可）。None なら thickness から単調テーパー
    width_keys: Sequence[tuple[float, float]] | None = None
    # 仮名 YAML elements[].id（ゲート接合参照用。漢字骨格は None）
    element_id: str | None = None


def _apply_slope(p0: Vec2, p1: Vec2, slope_deg: float) -> tuple[Vec2, Vec2]:
    """水平に近い線分を右上がりに傾ける（左端固定）。"""
    dx = p1.x - p0.x
    if abs(dx) < 1e-6:
        return p0, p1
    rise = math.tan(math.radians(slope_deg)) * dx
    # 元の中点 y を保ちつつ傾ける
    mid_y = (p0.y + p1.y) * 0.5
    half = rise * 0.5
    return Vec2(p0.x, mid_y + half), Vec2(p1.x, mid_y - half)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _screen_up_normal(direction: Vec2) -> Vec2:
    """進行方向に対し、SVG座標で画面上側を向く単位法線。"""
    n = direction.normalized().perpendicular().normalized()
    # SVG は Y 下向きなので、上側 = y 成分が負
    if n.y > 0:
        n = n * -1.0
    return n


def _make_uroko(tip: Vec2, direction: Vec2, half: float, p: MinchoParams) -> list[Vec2]:
    """
    横画右端のうろこ（三角形セリフ）。
    tip は骨格右端。進行方向は左→右。
    輪郭に凹み (uroko_dent) を入れてクラシックな食い込みを表現。
    """
    d = direction.normalized()
    up = _screen_up_normal(d)
    down = up * -1.0
    # 本体右端へ食い込ませる基点
    nest = tip - d * (p.uroko_width * 0.35)
    base_top = nest + up * half
    base_bot = nest + down * half
    # 明朝のうろこは右上に突き出す
    peak = tip + d * (p.uroko_width * 0.25) + up * (half + p.uroko_height)
    bottom = tip + d * (p.uroko_width * 0.05) + down * half
    # 凹み点（上辺の途中を内側＝下へ）
    dent = peak.lerp(base_top, 0.4) + down * p.uroko_dent + d * (p.uroko_dent * 0.25)
    outer = tip + d * (p.uroko_width * 0.5) + up * (half + p.uroko_height * 0.5)

    return [
        base_top,
        dent,
        peak,
        outer,
        bottom,
        base_bot,
        base_top,
    ]


def _make_uchikomi_horizontal(
    start: Vec2, direction: Vec2, half: float, p: MinchoParams
) -> list[Vec2]:
    """横画左端の打ち込み（斜めエントリー）。"""
    d = direction.normalized()
    up = _screen_up_normal(d)
    down = up * -1.0
    depth = p.uchikomi_depth
    ang = p.uchikomi_angle_deg
    # 本体左端へ食い込ませる
    nest = start + d * (depth * 0.45)
    top = nest + up * half
    bot = nest + down * half
    entry = start - d * depth + up * (half * 0.15)
    cut = start - d * (depth * 0.15) + up * half + (-d).rotated(-ang) * (depth * 0.75)
    return [entry, cut, top, bot, entry]


def build_vertical(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """縦画: 太い帯 + 上打ち込み + 下止め/はね。"""
    assert len(stroke.points) >= 2
    a, b = stroke.points[0], stroke.points[1]  # a=上, b=下
    # 上→下へ正規化
    if a.y > b.y:
        a, b = b, a
    thick = stroke.thickness or p.v_thickness
    half = thick * 0.5
    direction = (b - a).normalized()  # 下向き

    # 端物は本体に重ねる（隙間回避）。交差部のブーリアンは未実装。
    body_a = a + direction * 2.0
    body_b = b - direction * 2.0
    samples = smooth_tangents(sample_polyline([body_a, body_b], n_per_seg=40))

    # 下端でわずかに太らせる（止め感）
    half_widths: list[float] = []
    for i in range(len(samples)):
        t = i / max(1, len(samples) - 1)
        w = half
        if stroke.end_tag == EndTag.TOME and t > 0.85:
            w = half * _lerp(1.0, 1.12, (t - 0.85) / 0.15)
        half_widths.append(w)

    body = variable_width_outline(samples, half_widths, close=True)
    parts: list[list[Vec2]] = [body]

    if stroke.start_tag == EndTag.UCHIKOMI:
        parts.append(_make_uchikomi_vertical(a, half, p))

    if stroke.end_tag == EndTag.TOME:
        parts.append(_make_tome(b, half, p))
    elif stroke.end_tag == EndTag.HANE:
        parts.append(_make_hane(b, half, p))

    return parts


def _make_uchikomi_vertical(top: Vec2, half: float, p: MinchoParams) -> list[Vec2]:
    """縦画上端の打ち込み。"""
    depth = p.uchikomi_depth
    # 左上から右下へ斜めに入る（本体上端に食い込み）
    return [
        Vec2(top.x - half * 0.15, top.y - depth * 0.25),
        Vec2(top.x - half, top.y + depth * 0.15),
        Vec2(top.x - half, top.y + depth * 1.1),
        Vec2(top.x + half, top.y + depth * 0.7),
        Vec2(top.x + half * 0.9, top.y - depth * 0.1),
        Vec2(top.x - half * 0.15, top.y - depth * 0.25),
    ]


def _make_tome(bottom: Vec2, half: float, p: MinchoParams) -> list[Vec2]:
    """縦画下端の止め（右下がり斜めカット＋わずかな広がり）。"""
    s = p.tome_slant
    return [
        Vec2(bottom.x - half, bottom.y - s * 0.8),
        Vec2(bottom.x - half * 1.08, bottom.y + s * 0.1),
        Vec2(bottom.x + half * 1.12, bottom.y + s * 0.5),
        Vec2(bottom.x + half, bottom.y - s * 0.5),
        Vec2(bottom.x - half, bottom.y - s * 0.8),
    ]


def _make_hane(bottom: Vec2, half: float, p: MinchoParams) -> list[Vec2]:
    """左向きの鋭いテーパーのはね。"""
    L = p.hane_length
    ht = p.hane_thickness * 0.5
    # 根元は縦画下端に深く食い込ませる
    root_r = Vec2(bottom.x + half * 0.35, bottom.y - 28)
    root_l = Vec2(bottom.x - half * 0.95, bottom.y - 20)
    mid = Vec2(bottom.x - L * 0.55, bottom.y - L * 0.08)
    tip = Vec2(bottom.x - L, bottom.y - L * 0.22)
    return [
        root_l,
        Vec2(mid.x, mid.y - ht * 0.55),
        tip,
        Vec2(mid.x + 10, mid.y + ht * 1.15),
        Vec2(bottom.x + half * 0.2, bottom.y + 6),
        root_r,
        root_l,
    ]


def build_left_hara(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """左はらい: 3次ベジェ中心線、幅 根元→先端で root→0。"""
    pts = list(stroke.points)
    if len(pts) == 2:
        # 直線指定なら制御点を自動生成
        a, b = pts
        c1 = a.lerp(b, 0.33) + Vec2(-20, 30)
        c2 = a.lerp(b, 0.66) + Vec2(-10, 10)
        pts = [a, c1, c2, b]
    assert len(pts) == 4
    root_w = stroke.thickness or p.left_hara_root
    samples = smooth_tangents(sample_cubic(pts[0], pts[1], pts[2], pts[3], n=56))
    half_widths = []
    for i in range(len(samples)):
        t = i / max(1, len(samples) - 1)
        # 根元はやや丸く、先端は鋭く
        profile = (1.0 - _smoothstep(t)) ** 1.15
        half_widths.append(root_w * 0.5 * profile)
    outline = variable_width_outline(samples, half_widths, close=True)
    return [outline]


def build_right_hara(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """右はらい: 途中で膨らみ、先端で鋭く抜ける。"""
    pts = list(stroke.points)
    if len(pts) == 2:
        a, b = pts
        c1 = a.lerp(b, 0.3) + Vec2(30, 20)
        c2 = a.lerp(b, 0.7) + Vec2(40, -10)
        pts = [a, c1, c2, b]
    assert len(pts) == 4
    max_w = stroke.thickness or p.right_hara_max
    bulge_t = p.right_hara_bulge_t
    samples = smooth_tangents(sample_cubic(pts[0], pts[1], pts[2], pts[3], n=64))
    half_widths = []
    for i in range(len(samples)):
        t = i / max(1, len(samples) - 1)
        # 根元はやや細く → bulge_t で最大 → 先端 0
        if t <= bulge_t:
            u = t / bulge_t
            w = _lerp(0.55, 1.0, _smoothstep(u))
        else:
            u = (t - bulge_t) / max(1e-6, 1.0 - bulge_t)
            # 先端へ向けて急減衰
            w = (1.0 - _smoothstep(u)) ** 1.35
        half_widths.append(max_w * 0.5 * w)
    outline = variable_width_outline(samples, half_widths, close=True)
    return [outline]


def build_ten(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """点: 涙滴形（短い右下がりのはらい状）。"""
    pts = list(stroke.points)
    if len(pts) == 1:
        c = pts[0]
        a = c + Vec2(-p.ten_width * 0.15, -p.ten_length * 0.35)
        b = c + Vec2(p.ten_width * 0.35, p.ten_length * 0.45)
        c1 = a.lerp(b, 0.3) + Vec2(p.ten_width * 0.35, 0)
        c2 = a.lerp(b, 0.7) + Vec2(p.ten_width * 0.15, p.ten_length * 0.05)
        pts = [a, c1, c2, b]
    elif len(pts) == 2:
        a, b = pts
        c1 = a.lerp(b, 0.35) + Vec2(p.ten_width * 0.4, 0)
        c2 = a.lerp(b, 0.7) + Vec2(p.ten_width * 0.15, 8)
        pts = [a, c1, c2, b]
    assert len(pts) == 4
    max_w = p.ten_width
    samples = smooth_tangents(sample_cubic(pts[0], pts[1], pts[2], pts[3], n=40))
    half_widths = []
    for i in range(len(samples)):
        t = i / max(1, len(samples) - 1)
        # 涙滴: 根元付近で膨らみ、両端は細い
        bell = math.sin(math.pi * t) ** 1.1
        tip_taper = 1.0 - _smoothstep((t - 0.75) / 0.25) if t > 0.75 else 1.0
        root = 0.35 + 0.65 * _smoothstep(min(1.0, t / 0.25))
        half_widths.append(max_w * 0.5 * bell * tip_taper * root)
    # 根元を丸く閉じるため先頭半幅を少し残す
    if half_widths:
        half_widths[0] = max(half_widths[0], max_w * 0.12)
        half_widths[-1] = 0.0
    outline = variable_width_outline(samples, half_widths, close=True)
    return [outline]


def _default_kana_width_keys(half_max: float) -> list[tuple[float, float]]:
    """幅キー未指定時の仮名テーパー（入口やや細・中太・抜き先細）。"""
    return [
        (0.0, half_max * 0.45),
        (0.28, half_max),
        (0.70, half_max * 0.85),
        (1.0, half_max * 0.08),
    ]


def kana_max_half_width(stroke: SkeletonStroke, p: MinchoParams) -> float:
    if stroke.width_keys:
        return max(float(w) for _, w in stroke.width_keys)
    if stroke.thickness is not None:
        return stroke.thickness * 0.5
    return p.h_thickness * 0.5


def build_kana_curve(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """仮名曲線: cubic 列 → 弧長再サンプル → 幅プロファイル → 肉付け。

    仮名は RDP をかけない前提（bridge 側で passthrough）。端物テンプレは
    幅キーで近似し、専用パーツ生成は後続スパイクで足す。
    """
    pts = list(stroke.points)
    if len(pts) > KANA_MAX_SPINE_POINTS:
        raise ValueError(
            f"KANA_CURVE spine too many points: {len(pts)} > {KANA_MAX_SPINE_POINTS} "
            "(節点上限: 制御点込み 3n+1、n≤6)"
        )
    # 構文検証（3n+1）
    parse_cubic_chain(pts)
    dense = sample_cubic_chain(pts, n_per_seg=48)
    dense = smooth_tangents(dense)
    max_hw = kana_max_half_width(stroke, p)
    keys = (
        list(stroke.width_keys)
        if stroke.width_keys
        else _default_kana_width_keys(max_hw)
    )
    arc = resample_by_arclength(dense, n=KANA_ARCLENGTH_SAMPLES)
    samples = [(pos, tan) for pos, tan, _s in arc]
    half_widths = [interpolate_width_keys(s, keys) for _pos, _tan, s in arc]
    # 局所半幅に対する曲率ゲート（太い所だけ厳しく。先細り部は許容）
    radii = curvature_radii(samples)
    for i, (r, hw) in enumerate(zip(radii, half_widths)):
        floor_r = KANA_CURVATURE_RADIUS_FACTOR * hw
        if r < floor_r:
            s = arc[i][2]
            raise ValueError(
                f"KANA_CURVE curvature gate failed at s={s:.2f}: "
                f"radius={r:.2f} < {floor_r:.2f} (= {KANA_CURVATURE_RADIUS_FACTOR}×hw={hw:.2f}). "
                "骨格 YAML 側を緩めてください（エンジンは黙って補正しない）"
            )
    outline = variable_width_outline(samples, half_widths, close=True)
    return [outline]


def build_stroke(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """ストローク種別ごとにアウトライン（1本以上のポリゴン）を生成。"""
    if stroke.kind == StrokeKind.HORIZONTAL:
        return _build_horizontal_parts(stroke, p)
    if stroke.kind == StrokeKind.VERTICAL:
        return build_vertical(stroke, p)
    if stroke.kind == StrokeKind.LEFT_HARA:
        return build_left_hara(stroke, p)
    if stroke.kind == StrokeKind.RIGHT_HARA:
        return build_right_hara(stroke, p)
    if stroke.kind == StrokeKind.TEN:
        return build_ten(stroke, p)
    if stroke.kind == StrokeKind.KANA_CURVE:
        return build_kana_curve(stroke, p)
    raise ValueError(f"unknown stroke kind: {stroke.kind}")


def _build_horizontal_parts(stroke: SkeletonStroke, p: MinchoParams) -> list[list[Vec2]]:
    """横画を本体＋端物の複数ポリゴンとして返す。"""
    assert len(stroke.points) >= 2
    a, b = stroke.points[0], stroke.points[1]
    a, b = _apply_slope(a, b, p.h_slope_deg)
    thick = stroke.thickness or p.h_thickness
    half = thick * 0.5
    direction = (b - a).normalized()

    # 端物は本体に食い込ませて隙間を防ぐ（ブーリアン合成は行わない）
    body_a = a + direction * 2.0
    body_b = b - direction * 2.0
    if (body_b - body_a).length() < thick * 2:
        body_a, body_b = a, b

    samples = smooth_tangents(sample_polyline([body_a, body_b], n_per_seg=36))
    half_widths = [half] * len(samples)
    body = variable_width_outline(samples, half_widths, close=True)
    parts: list[list[Vec2]] = [body]

    if stroke.start_tag == EndTag.UCHIKOMI:
        parts.append(_make_uchikomi_horizontal(a, direction, half, p))
    if stroke.end_tag == EndTag.UROKO:
        parts.append(_make_uroko(b, direction, half, p))
    return parts


def strokes_to_svg_paths(parts: Sequence[Sequence[Vec2]]) -> str:
    return " ".join(polygon_to_svg_path(poly) for poly in parts if len(poly) >= 3)
