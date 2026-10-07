"""様式分離と、パイロットの形の検査。分離の閾値だけを凍結する。"""

from __future__ import annotations

import math
import statistics
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from engine.latin.build import GlyphOutline

_TARGETS = Path(__file__).resolve().parent / "targets" / "separation.yaml"


def separation_path() -> Path:
    return _TARGETS


def load_separation(path: Path | None = None) -> dict[str, Any]:
    raw = yaml.safe_load((path or _TARGETS).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("separation: mapping required")
    axes = tuple(raw["distance_axes"])
    styles = raw["styles"]
    span = {
        axis: (
            min(styles[name][axis] for name in styles),
            max(styles[name][axis] for name in styles),
        )
        for axis in axes
    }
    distances = pairwise_distances(styles, axes, span)
    nearest = min(distances.values())
    recorded = float(raw["nearest_distance"])
    if abs(nearest - recorded) > 1e-9:
        raise ValueError(f"separation: nearest distance {nearest} != frozen {recorded}")
    threshold = float(raw["min_distance"])
    if threshold > nearest + 1e-9:
        raise ValueError(
            f"separation: threshold {threshold} above the frozen nearest {nearest}"
        )
    return {
        "axes": axes,
        "styles": styles,
        "span": span,
        "distances": distances,
        "nearest_distance": recorded,
        "min_distance": threshold,
    }


def _vector(
    style: dict[str, float], axes: tuple[str, ...], span: dict[str, tuple[float, float]]
) -> list[float]:
    out: list[float] = []
    for axis in axes:
        lo, hi = span[axis]
        width = hi - lo
        out.append(0.0 if width == 0.0 else (float(style[axis]) - lo) / width)
    return out


def pairwise_distances(
    styles: dict[str, dict[str, float]],
    axes: tuple[str, ...],
    span: dict[str, tuple[float, float]],
) -> dict[tuple[str, str], float]:
    names = list(styles)
    vectors = {name: _vector(styles[name], axes, span) for name in names}
    distances: dict[tuple[str, str], float] = {}
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            gap = math.sqrt(
                sum(
                    (a - b) ** 2
                    for a, b in zip(vectors[left], vectors[right], strict=True)
                )
            )
            distances[(left, right)] = gap
    return distances


def assert_separated(
    measured: dict[str, dict[str, float]], frozen: dict[str, Any] | None = None
) -> None:
    """凍結した幅で測り、最近ペアが凍結距離未満なら ValueError。"""
    spec = frozen if frozen is not None else load_separation()
    distances = pairwise_distances(measured, spec["axes"], spec["span"])
    nearest = min(distances.items(), key=lambda item: item[1])
    if nearest[1] < spec["min_distance"] - 1e-9:
        pair = nearest[0]
        raise ValueError(
            f"G-SEP: {pair[0]}–{pair[1]} distance {nearest[1]:.4f} < {spec['min_distance']:.4f}"
        )


# オーバーシュートの帯は、様式 YAML の値 ± この幅。測った結果では凍結しない。
_OVERSHOOT_TOL = 1.0
# 縦ステムは、縁が垂直に近く、上下 40 でも同じ太さが続く墨。
_STEM_Y = (180.0, 250.0, 450.0, 520.0)
_STEM_SPAN = 40.0
_VERTICAL_DEG = 78.0


def _points(outline: GlyphOutline):
    return [
        point
        for contour, hole in zip(outline.contours, outline.holes, strict=True)
        if not hole
        for point in contour
    ]


def _box(outline: GlyphOutline) -> tuple[float, float, float, float]:
    points = _points(outline)
    return (
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def side_gaps(outline: GlyphOutline) -> tuple[float, float]:
    """墨の左端と、送り幅の右端から墨の右端まで。負なら字が隣に食い込む。"""
    xs = [
        point.x
        for contour, hole in zip(outline.contours, outline.holes, strict=True)
        if not hole
        for point in contour
    ]
    return min(xs), outline.advance - max(xs)


def line_gap_area(
    glyphs: list[GlyphOutline], *, y0: float = 0.0, y1: float = 700.0, step: float = 2.0
) -> float:
    """隣り合う字のあいだの白を、キャップハイトの帯で積む。"""
    total = 0.0
    y = y0
    while y < y1 - 1e-9:
        for left, right in pairwise(glyphs):
            before = _runs(left, y, vertical=False)
            after = _runs(right, y, vertical=False)
            if before and after:
                gap = (min(run[0] for run in after) + left.advance) - max(
                    run[1] for run in before
                )
                total += gap * step
        y += step
    return total


def ink_area(outline: GlyphOutline) -> float:
    """外形の面積から穴を引く。"""
    total = 0.0
    for contour, hole in zip(outline.contours, outline.holes, strict=True):
        signed = 0.0
        ring = list(contour)
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            signed += start.x * end.y - end.x * start.y
        area = abs(signed) / 2.0
        total += -area if hole else area
    return total


def _runs(
    outline: GlyphOutline, y: float, *, vertical: bool
) -> list[tuple[float, float]]:
    cuts: list[tuple[float, float]] = []
    for contour in outline.contours:
        ring = list(contour)
        for start, end in zip(ring, ring[1:] + ring[:1], strict=False):
            if (start.y - y) * (end.y - y) > 0.0 or abs(end.y - start.y) < 1e-9:
                continue
            t = (y - start.y) / (end.y - start.y)
            if not 0.0 <= t < 1.0:
                continue
            angle = abs(math.degrees(math.atan2(end.y - start.y, end.x - start.x)))
            angle = min(angle, 180.0 - angle)
            cuts.append((start.x + (end.x - start.x) * t, angle))
    cuts.sort()
    runs: list[tuple[float, float]] = []
    for index in range(0, len(cuts) - 1, 2):
        left, left_angle = cuts[index]
        right, right_angle = cuts[index + 1]
        if vertical and (left_angle < _VERTICAL_DEG or right_angle < _VERTICAL_DEG):
            continue
        if right > left:
            runs.append((left, right))
    return runs


def thinnest_run(outline: GlyphOutline, y: float) -> float:
    """y を横切る墨の、いちばん細い幅。"""
    runs = _runs(outline, y, vertical=False)
    if not runs:
        raise ValueError(f"{outline.glyph}: no ink at y={y}")
    return min(right - left for left, right in runs)


def overshoot_limit(resolved) -> tuple[str, float]:
    """build の付け方に合わせる。接合した碗（B）は平ら、開いた碗は丸、先端は尖り。"""
    cap = resolved.style.cap_height
    skeleton = resolved.skeleton
    if any("apex" in stroke.ends for stroke in skeleton.strokes):
        return "apex", resolved.style.overshoot["apex"] * cap
    joined = {join.a for join in skeleton.joins if join.type == "bowl_join"}
    if any(
        stroke.role == "bowl" and stroke.id not in joined for stroke in skeleton.strokes
    ):
        return "round", resolved.style.overshoot["round"] * cap
    return "flat", 0.0


def overshoot_violations(outline: GlyphOutline, resolved) -> list[str]:
    """G-O。墨のはみ出しが、様式の値から 1 UPM を超えた字を返す。"""
    _left, ymin, _right, ymax = _box(outline)
    above = ymax - resolved.style.cap_height
    below = -ymin
    kind, limit = overshoot_limit(resolved)
    if kind == "apex":
        deep, shallow = max(above, below), min(above, below)
        found = []
        if abs(deep - limit) > _OVERSHOOT_TOL:
            found.append(f"尖り {deep:.1f} が帯 {limit:.1f} の外")
        if abs(shallow) > _OVERSHOOT_TOL:
            found.append(f"尖りの反対側 {shallow:.1f}")
        return found
    return [
        f"{kind}の{label} {value:.1f} が帯 {limit:.1f} の外"
        for label, value in (("上", above), ("下", below))
        if abs(value - limit) > _OVERSHOOT_TOL
    ]


def metric_violations(outline: GlyphOutline, style) -> list[str]:
    """G-M。winAscent と winDescent は UFO で ascender と descender と同じ値。"""
    _left, ymin, _right, ymax = _box(outline)
    ascender = style.vertical["ascender"]
    descender = style.vertical["descender"]
    found = []
    if ymax > ascender:
        found.append(f"ascender {ymax:.1f} > {ascender:.1f}")
    if ymin < descender:
        found.append(f"descender {ymin:.1f} < {descender:.1f}")
    return found


def vertical_stem_widths(outline: GlyphOutline) -> list[float]:
    found: list[float] = []
    for y in _STEM_Y:
        here = _runs(outline, y, vertical=True)
        near = _runs(outline, y + _STEM_SPAN, vertical=True) + _runs(
            outline, y - _STEM_SPAN, vertical=True
        )
        for left, right in here:
            width = right - left
            mid = (left + right) / 2.0
            if any(
                abs((other_left + other_right) / 2.0 - mid) < width
                and abs((other_right - other_left) - width) <= 0.15 * width
                for other_left, other_right in near
            ):
                found.append(width)
    return found


def stem_set_violations(outlines: dict[str, GlyphOutline]) -> list[str]:
    """G-SET の縦ステム。字の中央値が、セットの中央値から 5% を超えた字。

    コントラストと応力角は separation.yaml の記録を使い、ここでは凍結しない。
    """
    widths = {name: vertical_stem_widths(outline) for name, outline in outlines.items()}
    samples = [width for group in widths.values() for width in group]
    if not samples:
        return []
    middle = statistics.median(samples)
    return [
        name
        for name, group in widths.items()
        if group and abs(statistics.median(group) - middle) / middle > 0.05
    ]
