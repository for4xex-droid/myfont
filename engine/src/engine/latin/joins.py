"""接合。股の細めは半幅列の端を crotch_thin 倍まで落とす。"""

from __future__ import annotations


def taper_end(half_widths: list[float], *, at_start: bool, factor: float, fraction: float = 0.22) -> None:
    """端の半幅を factor 倍へ滑らかに寄せる。factor が 1 なら変えない。"""
    if factor == 1.0 or len(half_widths) < 3:
        return
    span = max(2, int(len(half_widths) * fraction))
    if at_start:
        for i in range(span):
            blend = 1.0 - i / span
            half_widths[i] *= (1.0 - blend) + factor * blend
        return
    last = len(half_widths) - 1
    for i in range(span):
        blend = 1.0 - i / span
        half_widths[last - i] *= (1.0 - blend) + factor * blend
