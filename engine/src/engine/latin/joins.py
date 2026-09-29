"""接合。股の細め、頂点の留め、幹への埋め込み。"""

from __future__ import annotations

from engine.geometry import Vec2


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


def _closest(point: Vec2, samples: list[tuple[Vec2, Vec2]]) -> tuple[float, Vec2, int] | None:
    best: tuple[float, Vec2, int] | None = None
    for i in range(len(samples) - 1):
        start = samples[i][0]
        end = samples[i + 1][0]
        chord = end - start
        length2 = chord.dot(chord)
        if length2 < 1e-12:
            proj = start
        else:
            t = max(0.0, min(1.0, (point - start).dot(chord) / length2))
            proj = start + chord * t
        dist = (point - proj).length()
        if best is None or dist < best[0]:
            best = (dist, proj, i)
    return best


def retract_end(
    samples: list[tuple[Vec2, Vec2]],
    widths: list[float],
    partner: list[tuple[Vec2, Vec2]],
    partner_widths: list[float],
    *,
    at_start: bool,
) -> tuple[list[tuple[Vec2, Vec2]], list[float]]:
    """端が相手の中心線を越えていたら、中心線との交点まで戻す。"""
    if len(samples) < 3 or len(partner) < 2:
        return samples, widths
    end_i = 0 if at_start else len(samples) - 1
    hit = _closest(samples[end_i][0], partner)
    if hit is None:
        return samples, widths
    dist, center, seg = hit
    partner_half = partner_widths[min(seg, len(partner_widths) - 1)]
    # 相手の太さ程度までは埋め込む。幹の端が交差する横画まで届く距離にはしない。
    reach = 1.5 * (widths[end_i] + partner_half)
    if dist > reach:
        return samples, widths
    normal = samples[len(samples) // 2][0] - center
    if normal.length() < 1e-6:
        return samples, widths
    normal = normal.normalized()

    def side(point: Vec2) -> float:
        return (point - center).dot(normal)

    pts = list(samples)
    ws = list(widths)
    if at_start:
        k = 0
        while k < len(pts) - 1 and side(pts[k][0]) < 0.0:
            k += 1
        if k == 0:
            return samples, widths
        p0, p1 = pts[k - 1][0], pts[k][0]
        s0, s1 = side(p0), side(p1)
        t = 0.0 if abs(s1 - s0) < 1e-9 else max(0.0, min(1.0, -s0 / (s1 - s0)))
        pos = p0.lerp(p1, t)
        return [(pos, pts[k][1])] + pts[k:], [ws[k - 1] + (ws[k] - ws[k - 1]) * t] + ws[k:]
    k = len(pts) - 1
    while k > 0 and side(pts[k][0]) < 0.0:
        k -= 1
    if k == len(pts) - 1:
        return samples, widths
    p0, p1 = pts[k][0], pts[k + 1][0]
    s0, s1 = side(p0), side(p1)
    t = 0.0 if abs(s1 - s0) < 1e-9 else max(0.0, min(1.0, -s0 / (s1 - s0)))
    pos = p0.lerp(p1, t)
    return pts[: k + 1] + [(pos, pts[k][1])], ws[: k + 1] + [ws[k] + (ws[k + 1] - ws[k]) * t]
