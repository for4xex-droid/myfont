"""折れ線輪郭を cubic にフィットし、直線スナップと開始点を固定する。"""

from __future__ import annotations

import math

from engine.curve_fit import ContourPath, fit_closed_contour
from engine.latin.build import GlyphOutline
from engine.latin.style import Style


def _signed_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1] - points[j][0] * points[i][1]
    return 0.5 * area


def _rotate_start(path: ContourPath) -> ContourPath:
    points = path.on_curve_points()
    if len(points) < 2 or len(path.segs) != len(points):
        return path
    index = min(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    if index == 0:
        return path
    return ContourPath(start=points[index], segs=path.segs[index:] + path.segs[:index])


def _near_axis(dx: float, dy: float, tol_deg: float) -> str | None:
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
    if angle > 90.0:
        angle = 180.0 - angle
    if angle <= tol_deg:
        return "h"
    if abs(90.0 - angle) <= tol_deg:
        return "v"
    return None


def _flat_enough(start: tuple[float, float], seg: tuple, end: tuple[float, float]) -> bool:
    """曲線でも、制御点が弦から 1 ユニット以内なら直線とみなす。"""
    if seg[0] == "L":
        return True
    chord_x = end[0] - start[0]
    chord_y = end[1] - start[1]
    length = math.hypot(chord_x, chord_y) or 1.0
    for cx, cy in ((seg[1], seg[2]), (seg[3], seg[4])):
        cross = abs((cx - start[0]) * chord_y - (cy - start[1]) * chord_x) / length
        if cross > 1.0:
            return False
    return True


def _snap(path: ContourPath, tol_deg: float) -> ContourPath:
    """すでに直線の区間だけ、軸から tol 度以内なら水平または垂直にする。"""
    points = path.on_curve_points()
    if len(points) < 2 or len(path.segs) != len(points):
        return path
    snapped = [points[0]]
    segs: list[tuple] = []
    for i, seg in enumerate(path.segs):
        start = snapped[-1]
        end = points[(i + 1) % len(points)]
        kind = _near_axis(end[0] - start[0], end[1] - start[1], tol_deg)
        if kind is not None and _flat_enough(start, seg, end):
            if kind == "h":
                end = (end[0], start[1])
            else:
                end = (start[0], end[1])
            segs.append(("L", end[0], end[1]))
        elif seg[0] == "L":
            segs.append(("L", end[0], end[1]))
        else:
            segs.append(("C", seg[1], seg[2], seg[3], seg[4], end[0], end[1]))
        snapped.append(end)
    return ContourPath(start=snapped[0], segs=segs)


def _round(path: ContourPath) -> ContourPath:
    def r(x: float, y: float) -> tuple[float, float]:
        return (float(round(x)), float(round(y)))

    return path.transform(r)


def _orient(path: ContourPath, *, hole: bool) -> ContourPath:
    area = _signed_area(path.on_curve_points())
    # Y 上向き。外形は反時計回り（正）、穴は時計回り（負）。
    if hole and area > 0.0:
        return path.reversed()
    if not hole and area < 0.0:
        return path.reversed()
    return path


def fit_outline(outline: GlyphOutline, style: Style) -> tuple[ContourPath, ...]:
    """様式の誤差上限でフィットする。節点上限はオンカーブ点で見る。"""
    curve = style.curve
    fitted: list[tuple[tuple[float, float], ContourPath]] = []
    for contour, hole in zip(outline.contours, outline.holes):
        points = [(p.x, p.y) for p in contour]
        path, _meta = fit_closed_contour(
            points,
            max_error_upm=float(curve["max_error"]),
            corner_deg=float(curve["corner_deg"]),
            max_anchors=int(curve["max_anchors_per_contour"]),
        )
        path = _orient(_round(_snap(_rotate_start(path), 0.5)), hole=hole)
        origin = min(path.on_curve_points(), key=lambda p: (p[1], p[0]))
        fitted.append((origin, path))
    fitted.sort(key=lambda item: item[0])
    return tuple(path for _origin, path in fitted)
