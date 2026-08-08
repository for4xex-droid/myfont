"""KAGE FlattenedStroke → prototype SkeletonStroke 写像（spike7）。

座標: KAGE 200×200 Y下 → prototype SVG 空間（Y下・UPM1000）へ ×5 のみ。
（製品エンジン移行時は §0.1 どおり Y反転が別途必要。本スパイクは prototype 互換。）
"""

from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "prototype"))
sys.path.insert(0, str(ROOT.parent / "spike2"))

from geometry import Vec2  # noqa: E402
from strokes import EndTag, SkeletonStroke, StrokeKind  # noqa: E402

from kage_parser import FlattenedStroke  # noqa: E402

log = logging.getLogger("spike7.mapper")

KAGE_SCALE = 5.0  # 200 → 1000


class FallbackKind(str, Enum):
    NONE = "none"
    BEND_SPLIT = "bend_split"
    COMPLEX_CURVE_CUBIC = "complex_curve_as_cubic"
    VERTICAL_SWEEP_AS_LEFT = "vertical_sweep_as_left_hara"
    SPECIAL_SKIP = "special_skip"
    OTSU_SPLIT = "otsu_split"
    UNKNOWN_AS_POLYLINE = "unknown_as_polyline"
    SHORT_CURVE_AS_TEN = "short_curve_as_ten"
    QUAD_TO_CUBIC = "quad_to_cubic"


@dataclass
class MapWarning:
    fallback: FallbackKind
    message: str
    kage_type: int
    start_tag: int
    end_tag: int


@dataclass
class MapResult:
    strokes: List[SkeletonStroke] = field(default_factory=list)
    warnings: List[MapWarning] = field(default_factory=list)
    skipped: int = 0


def kage_to_upm(p: Tuple[float, float]) -> Vec2:
    """KAGE点 → prototype SVG/UPM1000（Y下のまま ×5）。"""
    return Vec2(p[0] * KAGE_SCALE, p[1] * KAGE_SCALE)


def map_end_tag(tag: int, which: str) -> EndTag:
    """端点タグ写像（spike2/verify_c_mapping と整合）。"""
    table_start = {
        0: EndTag.NONE,
        2: EndTag.UCHIKOMI,
        4: EndTag.HANE,
        5: EndTag.TAPER,
        7: EndTag.NONE,
        8: EndTag.NONE,
        12: EndTag.UCHIKOMI,
        13: EndTag.NONE,
        22: EndTag.UCHIKOMI,
        23: EndTag.UCHIKOMI,
        24: EndTag.HANE,
        32: EndTag.UCHIKOMI,
    }
    table_end = {
        0: EndTag.NONE,
        2: EndTag.UROKO,
        4: EndTag.HANE,
        5: EndTag.TAPER,
        7: EndTag.TOME,
        8: EndTag.NONE,
        12: EndTag.NONE,
        13: EndTag.NONE,
        22: EndTag.TOME,
        23: EndTag.TOME,
        24: EndTag.HANE,
        32: EndTag.UCHIKOMI,
    }
    table = table_start if which == "start" else table_end
    if tag not in table:
        log.warning("unmapped endpoint tag %s (%s) → NONE", tag, which)
        return EndTag.NONE
    return table[tag]


def _hv_kind(p0: Vec2, p1: Vec2) -> StrokeKind:
    dx = abs(p1.x - p0.x)
    dy = abs(p1.y - p0.y)
    if dx >= dy:
        return StrokeKind.HORIZONTAL
    return StrokeKind.VERTICAL


def _normalize_hv_order(kind: StrokeKind, a: Vec2, b: Vec2) -> Tuple[Vec2, Vec2]:
    """横は左→右、縦は上→下。"""
    if kind == StrokeKind.HORIZONTAL:
        return (a, b) if a.x <= b.x else (b, a)
    return (a, b) if a.y <= b.y else (b, a)


def _quad_to_cubic(p0: Vec2, p1: Vec2, p2: Vec2) -> List[Vec2]:
    """2次ベジェ制御点3つ → 3次ベジェ4点（次数上げ）。"""
    c1 = p0 + (p1 - p0) * (2.0 / 3.0)
    c2 = p2 + (p1 - p2) * (2.0 / 3.0)
    return [p0, c1, c2, p2]


def _curve_kind(p0: Vec2, p_end: Vec2) -> Tuple[StrokeKind, Optional[FallbackKind]]:
    """曲線の種別判定。閾値は UPM 空間（KAGE値×SCALE）。"""
    dx = p_end.x - p0.x
    dy = p_end.y - p0.y
    # KAGE空間で dx<25, dy<40, len<55 相当
    if abs(dx) < 25 * KAGE_SCALE and abs(dy) < 40 * KAGE_SCALE:
        length = math.hypot(dx, dy)
        if length < 55 * KAGE_SCALE:
            return StrokeKind.TEN, FallbackKind.SHORT_CURVE_AS_TEN
    if dx < 0:
        return StrokeKind.LEFT_HARA, None
    return StrokeKind.RIGHT_HARA, None


def _fit_end_tags_for_kind(
    kind: StrokeKind,
    start: EndTag,
    end: EndTag,
    *,
    kage_start: int = -1,
    kage_end: int = -1,
) -> Tuple[EndTag, EndTag]:
    """prototype 肉付けが解釈するタグに丸める。

    KAGE は tag0（open）でも描画エンジン側で黙定ディテールを付けることが多い。
    prototype はタグ駆動のため、両端 tag0 のときだけ黙定を補う
    （横: uchikomi+uroko / 縦: uchikomi+tome）。
    """
    open_defaults = kage_start == 0 and kage_end == 0
    if kind == StrokeKind.HORIZONTAL:
        st = start if start == EndTag.UCHIKOMI else EndTag.NONE
        if end == EndTag.UROKO:
            et = EndTag.UROKO
        elif end in (EndTag.TOME, EndTag.HANE, EndTag.TAPER):
            et = EndTag.NONE
        elif open_defaults:
            et = EndTag.UROKO
        else:
            et = EndTag.NONE
        if open_defaults and st == EndTag.NONE:
            st = EndTag.UCHIKOMI
        return st, et
    if kind == StrokeKind.VERTICAL:
        st = start if start == EndTag.UCHIKOMI else EndTag.NONE
        if end in (EndTag.HANE, EndTag.TOME):
            et = end
        elif open_defaults:
            et = EndTag.TOME
        else:
            et = EndTag.NONE
        if open_defaults and st == EndTag.NONE:
            st = EndTag.UCHIKOMI
        return st, et
    return EndTag.NONE, EndTag.NONE


def map_flattened_strokes(flat: Sequence[FlattenedStroke]) -> MapResult:
    """展開済み KAGE 筆画列を prototype SkeletonStroke 列へ写像。"""
    result = MapResult()

    for fs in flat:
        pts_k = list(fs.points)
        if not pts_k:
            result.skipped += 1
            result.warnings.append(
                MapWarning(
                    FallbackKind.SPECIAL_SKIP,
                    "empty points",
                    fs.stroke_type,
                    fs.start_tag,
                    fs.end_tag,
                )
            )
            continue

        pts = [kage_to_upm(p) for p in pts_k]
        st0 = map_end_tag(fs.start_tag, "start")
        et0 = map_end_tag(fs.end_tag, "end")
        stype = fs.stroke_type

        if stype == 0:
            result.skipped += 1
            w = MapWarning(
                FallbackKind.SPECIAL_SKIP,
                "type0 special skipped",
                stype,
                fs.start_tag,
                fs.end_tag,
            )
            result.warnings.append(w)
            log.warning("%s: %s", w.fallback.value, w.message)
            continue

        if stype == 1:
            if len(pts) < 2:
                result.skipped += 1
                continue
            kind = _hv_kind(pts[0], pts[1])
            a, b = _normalize_hv_order(kind, pts[0], pts[1])
            # 正規化で向きが変わったらタグも入れ替え
            reversed_dir = (a.x, a.y) != (pts[0].x, pts[0].y)
            if reversed_dir:
                ks, ke = fs.end_tag, fs.start_tag
                st0 = map_end_tag(ks, "start")
                et0 = map_end_tag(ke, "end")
            else:
                ks, ke = fs.start_tag, fs.end_tag
                st0 = map_end_tag(ks, "start")
                et0 = map_end_tag(ke, "end")
            st, et = _fit_end_tags_for_kind(
                kind, st0, et0, kage_start=ks, kage_end=ke
            )
            result.strokes.append(
                SkeletonStroke(kind=kind, points=[a, b], start_tag=st, end_tag=et)
            )
            continue

        if stype == 3:
            # 折れ: p0-p1 / p1-p2 の2直線
            if len(pts) < 3:
                result.skipped += 1
                continue
            w = MapWarning(
                FallbackKind.BEND_SPLIT,
                "type3 bend → 2 straight segments",
                stype,
                fs.start_tag,
                fs.end_tag,
            )
            result.warnings.append(w)
            log.warning("%s: %s", w.fallback.value, w.message)
            for i, (a, b) in enumerate([(pts[0], pts[1]), (pts[1], pts[2])]):
                kind = _hv_kind(a, b)
                aa, bb = _normalize_hv_order(kind, a, b)
                if i == 0:
                    st, et = _fit_end_tags_for_kind(
                        kind, st0, EndTag.NONE,
                        kage_start=fs.start_tag, kage_end=-1,
                    )
                else:
                    st, et = _fit_end_tags_for_kind(
                        kind, EndTag.NONE, et0,
                        kage_start=-1, kage_end=fs.end_tag,
                    )
                result.strokes.append(
                    SkeletonStroke(kind=kind, points=[aa, bb], start_tag=st, end_tag=et)
                )
            continue

        if stype == 4:
            # 乙線: 3点を折れと同様に分割（近似）
            if len(pts) < 3:
                result.skipped += 1
                continue
            w = MapWarning(
                FallbackKind.OTSU_SPLIT,
                "type4 otsu → 2 segments (approx)",
                stype,
                fs.start_tag,
                fs.end_tag,
            )
            result.warnings.append(w)
            log.warning("%s: %s", w.fallback.value, w.message)
            for i, (a, b) in enumerate([(pts[0], pts[1]), (pts[1], pts[2])]):
                kind = _hv_kind(a, b)
                aa, bb = _normalize_hv_order(kind, a, b)
                if i == 0:
                    st, et = _fit_end_tags_for_kind(
                        kind, st0, EndTag.NONE,
                        kage_start=fs.start_tag, kage_end=-1,
                    )
                else:
                    st, et = _fit_end_tags_for_kind(
                        kind, EndTag.NONE, et0,
                        kage_start=-1, kage_end=fs.end_tag,
                    )
                result.strokes.append(
                    SkeletonStroke(kind=kind, points=[aa, bb], start_tag=st, end_tag=et)
                )
            continue

        if stype in (2, 6, 7):
            fb: Optional[FallbackKind] = None
            if stype == 2:
                if len(pts) < 3:
                    result.skipped += 1
                    continue
                cubic = _quad_to_cubic(pts[0], pts[1], pts[2])
                fb = FallbackKind.QUAD_TO_CUBIC
                kind, extra = _curve_kind(cubic[0], cubic[-1])
                if extra:
                    fb = extra
            elif stype == 6:
                if len(pts) < 4:
                    result.skipped += 1
                    continue
                cubic = pts[:4]
                fb = FallbackKind.COMPLEX_CURVE_CUBIC
                kind, extra = _curve_kind(cubic[0], cubic[-1])
                if extra:
                    fb = extra
                w = MapWarning(
                    FallbackKind.COMPLEX_CURVE_CUBIC,
                    "type6 complex_curve → cubic approx",
                    stype,
                    fs.start_tag,
                    fs.end_tag,
                )
                result.warnings.append(w)
                log.warning("%s: %s", w.fallback.value, w.message)
            else:  # 7
                if len(pts) < 3:
                    result.skipped += 1
                    continue
                cubic = _quad_to_cubic(pts[0], pts[1], pts[2])
                kind = StrokeKind.LEFT_HARA
                fb = FallbackKind.VERTICAL_SWEEP_AS_LEFT
                w = MapWarning(
                    FallbackKind.VERTICAL_SWEEP_AS_LEFT,
                    "type7 vertical_sweep → left_hara",
                    stype,
                    fs.start_tag,
                    fs.end_tag,
                )
                result.warnings.append(w)
                log.warning("%s: %s", w.fallback.value, w.message)

            if stype == 2 and fb == FallbackKind.QUAD_TO_CUBIC:
                # 通常の次数上げは軽微なので警告は DEBUG
                log.debug("quad→cubic for type2")
            elif stype == 2 and fb == FallbackKind.SHORT_CURVE_AS_TEN:
                result.warnings.append(
                    MapWarning(
                        FallbackKind.SHORT_CURVE_AS_TEN,
                        "short curve → ten",
                        stype,
                        fs.start_tag,
                        fs.end_tag,
                    )
                )
                log.warning("short_curve_as_ten")

            st, et = _fit_end_tags_for_kind(
                kind, st0, et0, kage_start=fs.start_tag, kage_end=fs.end_tag
            )
            if kind == StrokeKind.TEN:
                result.strokes.append(
                    SkeletonStroke(
                        kind=kind,
                        points=[cubic[0], cubic[-1]],
                        start_tag=EndTag.NONE,
                        end_tag=EndTag.NONE,
                    )
                )
            else:
                result.strokes.append(
                    SkeletonStroke(
                        kind=kind, points=cubic, start_tag=st, end_tag=et
                    )
                )
            continue

        # 未知タイプ: 端点を直線としてフォールバック
        if len(pts) >= 2:
            w = MapWarning(
                FallbackKind.UNKNOWN_AS_POLYLINE,
                f"unknown type{stype} → H/V polyline fallback",
                stype,
                fs.start_tag,
                fs.end_tag,
            )
            result.warnings.append(w)
            log.warning("%s: %s", w.fallback.value, w.message)
            kind = _hv_kind(pts[0], pts[-1])
            a, b = _normalize_hv_order(kind, pts[0], pts[-1])
            st, et = _fit_end_tags_for_kind(
                kind, st0, et0, kage_start=fs.start_tag, kage_end=fs.end_tag
            )
            result.strokes.append(
                SkeletonStroke(kind=kind, points=[a, b], start_tag=st, end_tag=et)
            )
        else:
            result.skipped += 1

    return result


def fallback_counts(warnings: Sequence[MapWarning]) -> dict:
    from collections import Counter

    return dict(Counter(w.fallback.value for w in warnings))
