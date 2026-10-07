"""ペンの半幅。mono は一定、nib は接線角で太る。role が角度より優先する。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Pen:
    type: str
    stem: float
    bar_ratio: float
    hairline: float
    theta_deg: float


def half_width(
    pen: Pen, role: str, tangent: float, *, slant_ratio: float | None = None
) -> float:
    """キャップハイト比の半幅。tangent は接線の絶対角（ラジアン）。

    nib は楕円ペン。θ は細い方向（長軸）。接線が θ と平行なとき hairline、
    直交するとき stem。幅は接線角について滑らかで、最細の所に角を作らない。
    thick / thin / bar / slant_thin はこの式より優先する。run は式のまま。
    slant_thin は幹 × 様式の比。角度でもヘアラインでも決まらない。
    """
    if role == "slant_thin":
        if slant_ratio is None:
            raise ValueError("slant_thin requires slant_ratio")
        return pen.stem * slant_ratio / 2.0
    if pen.type == "mono":
        full = pen.stem * (pen.bar_ratio if role == "bar" else 1.0)
        return full / 2.0
    if role == "thick":
        return pen.stem / 2.0
    if role == "thin":
        return pen.hairline / 2.0
    if role == "bar":
        return pen.stem * pen.bar_ratio / 2.0
    theta = math.radians(pen.theta_deg)
    along = tangent - theta
    return math.hypot(pen.stem * math.sin(along), pen.hairline * math.cos(along)) / 2.0
