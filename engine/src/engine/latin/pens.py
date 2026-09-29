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


def half_width(pen: Pen, role: str, tangent: float) -> float:
    """キャップハイト比の半幅。tangent は接線の絶対角（ラジアン）。

    nib の θ は細い方向（nib の長軸）。接線が θ と平行なとき最も細く、
    θ に直交する接線のとき最も太い。直線の太細は role がこの式より優先する。
    """
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
    span = pen.stem - pen.hairline
    return (pen.hairline + span * abs(math.sin(tangent - theta))) / 2.0
