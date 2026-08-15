"""完成輪郭の等方スケール＋LSB 合わせ（計画§3）。"""

from __future__ import annotations

from typing import Any, Sequence

from engine.kana.schema import EmFitSpec

Point = tuple[float, float]


def font_bounds(contours: Sequence[Sequence[Point]]) -> tuple[float, float, float, float]:
    xs = [p[0] for c in contours for p in c]
    ys = [p[1] for c in contours for p in c]
    if not xs:
        raise ValueError("em_fit: empty contours")
    return min(xs), min(ys), max(xs), max(ys)


def path_bounds(paths: Sequence[Any]) -> tuple[float, float, float, float]:
    """on-curve と cubic 制御点を含む bbox（凸包 ⊇ 曲線）。"""
    xs: list[float] = []
    ys: list[float] = []
    for path in paths:
        xs.append(float(path.start[0]))
        ys.append(float(path.start[1]))
        for seg in path.segs:
            if seg[0] == "L":
                xs.append(float(seg[1]))
                ys.append(float(seg[2]))
            else:
                for i in (1, 3, 5):
                    xs.append(float(seg[i]))
                    ys.append(float(seg[i + 1]))
    if not xs:
        raise ValueError("em_fit: empty paths")
    return min(xs), min(ys), max(xs), max(ys)


def em_fit_transform(
    spec: EmFitSpec,
    contours: Sequence[Sequence[Point]] | None = None,
    *,
    bounds: tuple[float, float, float, float] | None = None,
):
    """bbox 中心で等方スケールし、xmin を target_lsb へ。xf(x,y) を返す。"""
    if bounds is None:
        if contours is None:
            raise ValueError("em_fit: contours or bounds required")
        xmin, ymin, xmax, ymax = font_bounds(contours)
    else:
        xmin, ymin, xmax, ymax = bounds
    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)
    s = spec.scale
    new_xmin = cx + s * (xmin - cx)
    dx = spec.target_lsb - new_xmin

    def xf(x: float, y: float) -> Point:
        return (cx + s * (x - cx) + dx, cy + s * (y - cy))

    y0 = cy + s * (ymin - cy)
    y1 = cy + s * (ymax - cy)
    if y0 < -1.0 or y1 > 1001.0:
        raise ValueError(
            f"em_fit: scaled y [{y0:.1f}, {y1:.1f}] leaves 0–1000"
        )
    return xf


def apply_em_fit_contours(
    spec: EmFitSpec, contours: Sequence[Sequence[Point]]
) -> list[list[Point]]:
    xf = em_fit_transform(spec, contours)
    return [[xf(x, y) for x, y in c] for c in contours]
