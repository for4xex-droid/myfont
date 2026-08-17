#!/usr/bin/env python3
"""抽出したステム＋端物テンプレだけで組み直す。正本は書かない。

はらいは残差の生コピーではなく、左右輪郭を弧長で間引いた点列。
中心線＋対称半幅は曲がった画で太るので使わない。


例:
  engine/.venv/bin/python scripts/rebuild_from_elements.py --chars 十二三口日
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from pathops import Path as OpsPath
from pathops import PathVerb, difference, intersection, xor
from engine.geometry import Vec2, sample_polyline, variable_width_outline

from extract_ref_elements import (
    STEM_INK_MIN,
    _ink_frac,
    combine,
    extract_char,
    rect_path,
    union,
)
from reproduce_ref import (
    INK,
    OUT_DEFAULT,
    REF_DEFAULT,
    assert_throwaway,
    iou,
    pack_bbox,
    render_em,
    uniname,
)

SCRATCH = OUT_DEFAULT / "_scratch"

# 十・二・三の残差から取った比。輪郭点は持たない。
UROKO_BOTTOM_FRAC = 0.91
UROKO_TIP_Y_FRAC = 0.20
UROKO_PEAK_X_FRAC = 0.43
TOP_CAP_RIGHT_Y_FRAC = 0.56
# 口・日の右上肩。棒うろこより低い。
BOX_FLARE = 0.55
BOX_PEAK_X = 0.39
BOX_PEAK_H = 1.98
TOP_LEFT_H = 1.40
HARA_SPINE_K = 96
# 箱うろこの高さ比。これより大きい Y ギャップだけ開いた T とみなす。
OPEN_T_GAP_OVER_H = 3.3
# 開いた十字。これ超のギャップは別部品（国の中の玉）。木は 3.3h。
OPEN_CROSS_GAP_OVER_H = 3.5
# 半幅がこれ超（EM）なら1本の中心線を拒否。0.10 だと永の磔頭（≈0.086em）が通る。
HARA_HALF_MAX_EM = 0.08
HARA_PINCH_DEPTH = 2
HARA_PINCH_RATIO = 0.65


def _is_junction(term: dict, row: dict, exact: OpsPath | None = None) -> bool:
    b = term.get("bounds")
    if not b:
        return False
    w, h = b[2] - b[0], b[3] - b[1]
    ht = row["h_thickness"] or 50.0
    vt = row["v_thickness"] or ht * 2.5
    if not (w <= vt * 1.15 and h <= ht * 1.15):
        return False
    # 打ち込みは半矩形（インク率 0.5）。十字の角はインクがある。
    if exact is not None and _ink_frac(exact, *b) < STEM_INK_MIN:
        return False
    return True


def merge_collinear(stems: list[dict]) -> list[dict]:
    hs = [dict(s) for s in stems if s["kind"] == "h"]
    vs = [dict(s) for s in stems if s["kind"] == "v"]
    max_th = max([s["thickness"] for s in stems] + [1.0])

    def _finish(p: dict, axis: str) -> None:
        if axis == "h":
            p["length"] = round(p["x1"] - p["x0"], 2)
            p["thickness"] = round(p["y1"] - p["y0"], 2)
        else:
            p["length"] = round(p["y1"] - p["y0"], 2)
            p["thickness"] = round(p["x1"] - p["x0"], 2)

    def _can_join(p: dict, s: dict, axis: str) -> bool:
        if axis == "h":
            aligned = abs(p["y0"] - s["y0"]) <= 4 and abs(p["y1"] - s["y1"]) <= 4
            gap = max(s["x0"] - p["x1"], p["x0"] - s["x1"])
        else:
            aligned = abs(p["x0"] - s["x0"]) <= 4 and abs(p["x1"] - s["x1"]) <= 4
            gap = max(s["y0"] - p["y1"], p["y0"] - s["y1"])
        return aligned and gap <= max_th * 1.2

    def _merge(items: list[dict], axis: str) -> list[dict]:
        out: list[dict] = []
        for s in items:
            hit = None
            for p in out:
                if _can_join(p, s, axis):
                    hit = p
                    break
            if hit is None:
                out.append(s)
                continue
            hit["x0"] = min(hit["x0"], s["x0"])
            hit["y0"] = min(hit["y0"], s["y0"])
            hit["x1"] = max(hit["x1"], s["x1"])
            hit["y1"] = max(hit["y1"], s["y1"])
            _finish(hit, axis)
        return out

    return _merge(hs, "h") + _merge(vs, "v")


def absorb_junctions(stems: list[dict], junctions: list[dict]) -> list[dict]:
    out = [dict(s) for s in stems]
    for j in junctions:
        b = j["bounds"]
        x0, y0, x1, y1 = b
        for s in out:
            if s["kind"] == "h" and abs(s["y0"] - y0) <= 6 and abs(s["y1"] - y1) <= 6:
                s["x0"] = min(s["x0"], x0)
                s["x1"] = max(s["x1"], x1)
                s["length"] = round(s["x1"] - s["x0"], 2)
            if s["kind"] == "v" and abs(s["x0"] - x0) <= 6 and abs(s["x1"] - x1) <= 6:
                s["y0"] = min(s["y0"], y0)
                s["y1"] = max(s["y1"], y1)
                s["length"] = round(s["y1"] - s["y0"], 2)
    return out


def absorb_extensions(
    stems: list[dict],
    terms: list[dict],
    exact: OpsPath | None = None,
) -> tuple[list[dict], list[dict]]:
    """ステム幅に揃った矩形残差は脚・延長としてステムに戻す。

    打ち込み（半矩形）は伸ばすと空欄を塗るので残す。
    """
    out = [dict(s) for s in stems]
    leftover = []
    for t in terms:
        b = t.get("bounds")
        if not b:
            leftover.append(t)
            continue
        if exact is not None and _ink_frac(exact, *b) < STEM_INK_MIN:
            leftover.append(t)
            continue
        taken = False
        for s in out:
            if s["kind"] == "v" and abs(s["x0"] - b[0]) <= 8 and abs(s["x1"] - b[2]) <= 8:
                s["y0"] = min(s["y0"], b[1])
                s["y1"] = max(s["y1"], b[3])
                s["length"] = round(s["y1"] - s["y0"], 2)
                taken = True
                break
            if s["kind"] == "h" and abs(s["y0"] - b[1]) <= 8 and abs(s["y1"] - b[3]) <= 8:
                s["x0"] = min(s["x0"], b[0])
                s["x1"] = max(s["x1"], b[2])
                s["length"] = round(s["x1"] - s["x0"], 2)
                taken = True
                break
        if not taken:
            leftover.append(t)
    return out, leftover


def fill_corners(stems: list[dict]) -> list[dict]:
    out = [dict(s) for s in stems]
    hs = [s for s in out if s["kind"] == "h"]
    vs = [s for s in out if s["kind"] == "v"]
    for h in hs:
        for v in vs:
            y_gap = max(0.0, max(h["y0"], v["y0"]) - min(h["y1"], v["y1"]))
            if y_gap > h["thickness"] * 0.7:
                continue
            if 0 <= v["x0"] - h["x1"] <= v["thickness"] * 1.15:
                h["x1"] = v["x1"]
            if 0 <= h["x0"] - v["x1"] <= v["thickness"] * 1.15:
                h["x0"] = v["x0"]
            x_gap = max(0.0, max(h["x0"], v["x0"]) - min(h["x1"], v["x1"]))
            if x_gap > v["thickness"] * 0.7:
                continue
            if 0 <= h["y0"] - v["y1"] <= h["thickness"] * 1.15:
                v["y1"] = h["y1"]
            if 0 <= v["y0"] - h["y1"] <= h["thickness"] * 1.15:
                v["y0"] = h["y0"]
        h["length"] = round(h["x1"] - h["x0"], 2)
    for v in vs:
        v["length"] = round(v["y1"] - v["y0"], 2)
    return out


def _junction_gap_ink(exact: OpsPath | None, v: dict, h: dict, *, up: bool) -> float:
    """伸ばす区間だけ見る。横画本体を含めると空欄が平均で通る。"""
    if exact is None:
        return 1.0
    if up:
        y0, y1 = v["y1"], h["y0"]
    else:
        y0, y1 = h["y1"], v["y0"]
    if y1 <= y0 + 1:
        return 1.0
    return _ink_frac(exact, v["x0"], y0, v["x1"], y1)


def close_open_junctions(stems: list[dict], exact: OpsPath | None = None) -> list[dict]:
    """開いた十字・開いた T を閉じる。遠い横画は別部品なので触らない。

    ギャップが空欄なら伸ばさない（車の腰。田のマスはインクがあるので閉じる）。
    """
    out = [dict(s) for s in stems]
    hs = [s for s in out if s["kind"] == "h"]
    vs = [s for s in out if s["kind"] == "v"]
    vt = max([s["thickness"] for s in vs] or [110.0])

    def _apply(v: dict, h: dict, y_gap: float, *, up: bool, is_cross: bool, is_t: bool, x_adj_r: bool, x_adj_l: bool) -> None:
        if is_cross and 0 < y_gap <= OPEN_CROSS_GAP_OVER_H * h["thickness"]:
            if _junction_gap_ink(exact, v, h, up=up) < STEM_INK_MIN:
                return
            if up:
                v["y1"] = h["y1"]
            else:
                v["y0"] = h["y0"]
        elif is_t and y_gap > OPEN_T_GAP_OVER_H * h["thickness"]:
            if _junction_gap_ink(exact, v, h, up=up) < STEM_INK_MIN:
                return
            if up:
                v["y1"] = h["y1"]
            else:
                v["y0"] = h["y0"]
            if x_adj_r:
                h["x1"] = v["x1"]
            if x_adj_l:
                h["x0"] = v["x0"]

    for v in vs:
        up: list[tuple] = []
        down: list[tuple] = []
        for h in hs:
            x_overlap = min(h["x1"], v["x1"]) - max(h["x0"], v["x0"])
            x_adj_r = 0 <= v["x0"] - h["x1"] <= vt * 1.15
            x_adj_l = 0 <= h["x0"] - v["x1"] <= vt * 1.15
            is_cross = x_overlap > 0
            is_t = x_adj_r or x_adj_l
            if not (is_cross or is_t):
                continue
            if h["y0"] >= v["y1"]:
                up.append((h["y0"] - v["y1"], h, is_cross, is_t, x_adj_r, x_adj_l))
            if v["y0"] >= h["y1"]:
                down.append((v["y0"] - h["y1"], h, is_cross, is_t, x_adj_r, x_adj_l))
        if up:
            y_gap, h, is_cross, is_t, x_adj_r, x_adj_l = min(up, key=lambda t: t[0])
            _apply(v, h, y_gap, up=True, is_cross=is_cross, is_t=is_t, x_adj_r=x_adj_r, x_adj_l=x_adj_l)
        if down:
            y_gap, h, is_cross, is_t, x_adj_r, x_adj_l = min(down, key=lambda t: t[0])
            _apply(v, h, y_gap, up=False, is_cross=is_cross, is_t=is_t, x_adj_r=x_adj_r, x_adj_l=x_adj_l)
        v["length"] = round(v["y1"] - v["y0"], 2)
        v["thickness"] = round(v["x1"] - v["x0"], 2)
    for h in hs:
        h["length"] = round(h["x1"] - h["x0"], 2)
        h["thickness"] = round(h["y1"] - h["y0"], 2)
    return out


def _nearest_stem(term: dict, stems: list[dict], kind: str | None = None) -> dict | None:
    b = term["bounds"]
    cx, cy = 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])
    best = None
    best_d = 1e18
    for s in stems:
        if kind and s["kind"] != kind:
            continue
        dx = max(s["x0"] - cx, 0.0, cx - s["x1"])
        dy = max(s["y0"] - cy, 0.0, cy - s["y1"])
        d = dx * dx + dy * dy
        if d < best_d:
            best, best_d = s, d
    return best


def _poly_path(pts: list[Vec2]) -> OpsPath:
    p = OpsPath()
    pen = p.getPen()
    pen.moveTo((pts[0].x, pts[0].y))
    last = pts[0]
    for pt in pts[1:]:
        if abs(pt.x - last.x) < 1e-6 and abs(pt.y - last.y) < 1e-6:
            continue
        pen.lineTo((pt.x, pt.y))
        last = pt
    pen.closePath()
    return p


def _uroko_poly(stem: dict, bounds: list[float]) -> list[Vec2]:
    _x0, y0, x1, y1 = bounds
    w = max(1.0, x1 - stem["x1"])
    h = max(1.0, y1 - stem["y0"])
    return [
        Vec2(stem["x1"], stem["y1"]),
        Vec2(stem["x1"], stem["y0"]),
        Vec2(stem["x1"] + UROKO_BOTTOM_FRAC * w, stem["y0"]),
        Vec2(stem["x1"] + w, stem["y0"] + UROKO_TIP_Y_FRAC * h),
        Vec2(stem["x1"] + UROKO_PEAK_X_FRAC * w, stem["y0"] + h),
    ]


def _top_cap_poly(stem: dict, bounds: list[float]) -> list[Vec2]:
    _x0, _y0, x1, y1 = bounds
    h = max(1.0, y1 - stem["y1"])
    return [
        Vec2(stem["x0"], stem["y1"]),
        Vec2(stem["x1"], stem["y1"]),
        Vec2(x1, stem["y1"] + TOP_CAP_RIGHT_Y_FRAC * h),
        Vec2(x1, y1),
        Vec2(stem["x0"], y1),
    ]


def _box_uroko_poly(h: dict, v: dict) -> list[Vec2]:
    flare = BOX_FLARE * v["thickness"]
    peak_x = h["x1"] + BOX_PEAK_X * (v["x1"] + flare - h["x1"])
    peak_y = h["y1"] + BOX_PEAK_H * h["thickness"]
    return [
        Vec2(v["x1"], v["y1"]),
        Vec2(v["x1"] + flare, v["y1"] + 0.6 * h["thickness"]),
        Vec2(v["x1"] + flare, h["y1"]),
        Vec2(peak_x, peak_y),
        Vec2(h["x1"], h["y1"]),
        Vec2(h["x1"], h["y0"]),
        Vec2(v["x0"], h["y0"]),
        Vec2(v["x0"], v["y1"]),
    ]


def _top_left_cap(v: dict, h: dict) -> list[Vec2]:
    return [
        Vec2(v["x1"], h["y1"]),
        Vec2(v["x0"], h["y1"]),
        Vec2(v["x0"], h["y1"] + TOP_LEFT_H * h["thickness"]),
    ]


def _hara_band(bounds: list[float], *, left: bool) -> list[Vec2]:
    """斜画の膨らみ帯。直線帯の天井は IoU≈0.24。一次の膨らみで≈0.47。"""
    import math

    x0, y0, x1, y1 = bounds
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    if left:
        a = (x1 - 0.08 * w, y1 - 0.03 * h)
        b = (x0 + 0.04 * w, y0 + 0.04 * h)
        sign = 1.0
    else:
        a = (x0 + 0.08 * w, y1 - 0.03 * h)
        b = (x1 - 0.04 * w, y0 + 0.04 * h)
        sign = -1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    half0, half1, bulge = 0.12 * w, 0.10 * w, 0.24 * w
    pts = []
    for t, half in ((0.0, half0), (0.5, 0.5 * (half0 + half1)), (1.0, half1)):
        bend = sign * bulge * 4 * t * (1 - t)
        px = a[0] + t * dx + bend * nx
        py = a[1] + t * dy + bend * ny
        pts.append((Vec2(px + nx * half, py + ny * half), Vec2(px - nx * half, py - ny * half)))
    return [pts[0][0], pts[1][0], pts[2][0], pts[2][1], pts[1][1], pts[0][1]]


def _hara_pair_polys(bounds: list[float]) -> list[list[Vec2]]:
    x0, y0, x1, y1 = bounds
    mx = 0.5 * (x0 + x1)
    left_b = [x0, y0, mx + 0.04 * (x1 - x0), y1]
    right_b = [mx - 0.04 * (x1 - x0), y0, x1, y1]
    return [_hara_band(left_b, left=True), _hara_band(right_b, left=False)]


def _ops_rings(path: OpsPath) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            if cur:
                rings.append(cur)
            cur = [pts[0]]
        elif verb == PathVerb.LINE:
            cur.append(pts[0])
        elif verb == PathVerb.QUAD:
            p0 = cur[-1]
            ctrl, p1 = pts[0], pts[1]
            for i in range(1, 9):
                t = i / 8
                u = 1 - t
                cur.append(
                    (
                        u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                        u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1],
                    )
                )
        elif verb == PathVerb.CLOSE:
            if cur:
                rings.append(cur)
            cur = []
    if cur:
        rings.append(cur)
    return rings


def _resample_chain(chain: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    if len(chain) < 2:
        return chain
    segs = []
    total = 0.0
    for i in range(len(chain) - 1):
        d = math.hypot(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
        segs.append(d)
        total += d
    if total <= 0:
        return [chain[0]] * n
    out = []
    for k in range(n):
        target = (k / (n - 1)) * total
        acc = 0.0
        for i, d in enumerate(segs):
            if acc + d >= target or i == len(segs) - 1:
                u = 0.0 if d == 0 else (target - acc) / d
                out.append(
                    (
                        chain[i][0] + u * (chain[i + 1][0] - chain[i][0]),
                        chain[i][1] + u * (chain[i + 1][1] - chain[i][1]),
                    )
                )
                break
            acc += d
    return out


def _resample_by_proj(
    chain: list[tuple[float, float]],
    origin: tuple[float, float],
    axis: tuple[float, float],
    n: int,
) -> list[tuple[float, float]]:
    """弧長ではなく軸への投影でサンプルする。曲がった画で対がずれない。"""
    dx, dy = axis
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    keyed: list[tuple[float, float, float]] = []
    for x, y in chain:
        t = (x - origin[0]) * ux + (y - origin[1]) * uy
        keyed.append((t, x, y))
    keyed.sort()
    pts: list[tuple[float, float, float]] = []
    for t, x, y in keyed:
        if pts and abs(t - pts[-1][0]) < 1e-6:
            pts[-1] = (t, x, y)
        else:
            pts.append((t, x, y))
    if len(pts) < 2:
        return [(p[1], p[2]) for p in pts] * max(1, n)
    t0, t1 = pts[0][0], pts[-1][0]
    out: list[tuple[float, float]] = []
    for i in range(n):
        target = t0 + (t1 - t0) * i / (n - 1)
        for j in range(len(pts) - 1):
            a, b = pts[j], pts[j + 1]
            if b[0] >= target or j == len(pts) - 2:
                span = b[0] - a[0]
                u = 0.0 if span == 0 else (target - a[0]) / span
                out.append((a[1] + u * (b[1] - a[1]), a[2] + u * (b[2] - a[2])))
                break
    return out


def _split_sides(ring: list[tuple[float, float]]):
    pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    if len(pts) < 6:
        return None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    sxx = syy = sxy = 0.0
    for x, y in pts:
        sxx += (x - mx) ** 2
        syy += (y - my) ** 2
        sxy += (x - mx) * (y - my)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    dx, dy = math.cos(ang), math.sin(ang)
    proj = [((x - mx) * dx + (y - my) * dy, i) for i, (x, y) in enumerate(pts)]
    i0 = min(proj)[1]
    i1 = max(proj)[1]
    n = len(pts)

    def walk(a: int, b: int):
        out = []
        i = a
        while True:
            out.append(pts[i])
            if i == b:
                break
            i = (i + 1) % n
            if len(out) > n:
                break
        return out

    a, b = walk(i0, i1), walk(i1, i0)
    if len(a) < 3 or len(b) < 3:
        return None
    if math.hypot(a[0][0] - b[-1][0], a[0][1] - b[-1][1]) < math.hypot(
        a[0][0] - b[0][0], a[0][1] - b[0][1]
    ):
        b = list(reversed(b))
    return a, b


def fit_hara_spine(ring: list[tuple[float, float]], k: int = HARA_SPINE_K):
    sides = _split_sides(ring)
    if sides is None:
        return None
    a, b = sides
    origin = ((a[0][0] + b[0][0]) / 2, (a[0][1] + b[0][1]) / 2)
    axis = (
        (a[-1][0] + b[-1][0]) / 2 - origin[0],
        (a[-1][1] + b[-1][1]) / 2 - origin[1],
    )
    n = max(24, k * 3)
    ra = _resample_by_proj(a, origin, axis, n)
    rb = _resample_by_proj(b, origin, axis, n)
    spine = []
    half = []
    for p, q in zip(ra, rb):
        spine.append(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
        half.append(0.5 * math.hypot(p[0] - q[0], p[1] - q[1]))
    idxs = [round(i * (len(spine) - 1) / (k - 1)) for i in range(k)]
    return [spine[i] for i in idxs], [half[i] for i in idxs]


def spine_is_simple(half: list[float], upm: float) -> bool:
    vals = [h for h in half if h > 1]
    if not vals:
        return False
    return max(vals) <= HARA_HALF_MAX_EM * upm


def _scan_width(ring: list[tuple[float, float]], y: float) -> float:
    pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    xs: list[float] = []
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
            t = (y - y0) / (y1 - y0)
            xs.append(x0 + t * (x1 - x0))
    if len(xs) < 2:
        return 0.0
    return max(xs) - min(xs)


def pinch_y(ring: list[tuple[float, float]]) -> float | None:
    """残差の中段で幅がくびれる Y。融合ストロークを切る。"""
    b = _ring_bounds(ring)
    height = b[3] - b[1]
    if height < 40:
        return None
    ys = [b[1] + height * (0.25 + 0.5 * i / 23) for i in range(24)]
    widths = [(y, _scan_width(ring, y)) for y in ys]
    positive = [w for _, w in widths if w > 1]
    if len(positive) < 6:
        return None
    peak = max(positive)
    y, w = min(widths, key=lambda t: t[1] if t[1] > 1 else 1e18)
    if w <= 1 or w > HARA_PINCH_RATIO * peak:
        return None
    return y


def _clip_ring_at_y(ring: list[tuple[float, float]], y: float) -> list[list[tuple[float, float]]]:
    b = _ring_bounds(ring)
    rp = OpsPath()
    pen = rp.getPen()
    pen.moveTo(ring[0])
    for p in ring[1:]:
        pen.lineTo(p)
    pen.closePath()

    def _rect(y0: float, y1: float) -> OpsPath:
        p = OpsPath()
        q = p.getPen()
        q.moveTo((b[0] - 20, y0))
        q.lineTo((b[2] + 20, y0))
        q.lineTo((b[2] + 20, y1))
        q.lineTo((b[0] - 20, y1))
        q.closePath()
        return p

    lo, hi = OpsPath(), OpsPath()
    intersection([rp], [_rect(b[1] - 20, y)], lo.getPen(), fix_winding=True)
    intersection([rp], [_rect(y, b[3] + 20)], hi.getPen(), fix_winding=True)
    return [r for r in _ops_rings(lo) + _ops_rings(hi) if len(r) >= 8]


def paths_from_hara_ring(
    ring: list[tuple[float, float]],
    upm: float,
    depth: int = 0,
) -> list[OpsPath]:
    fitted = fit_hara_spine(ring)
    sides = _split_sides(ring)
    side_path = outline_from_sides(*sides) if sides is not None else None
    if fitted is not None and spine_is_simple(fitted[1], upm) and side_path is not None:
        return [side_path]
    if depth >= HARA_PINCH_DEPTH:
        return [side_path] if side_path is not None else []
    y = pinch_y(ring)
    if y is None:
        return [side_path] if side_path is not None else []
    out: list[OpsPath] = []
    for part in _clip_ring_at_y(ring, y):
        out.extend(paths_from_hara_ring(part, upm, depth + 1))
    # 心の下画: くびれで切るとフックが欠ける。残差自身との IoU が左右より悪ければ切らない。
    if side_path is not None and out:
        pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
        ring_path = _poly_path([Vec2(*p) for p in pts])
        pinched = combine(out, union)
        if vector_iou(ring_path, pinched)[0] + 0.005 < vector_iou(ring_path, side_path)[0]:
            return [side_path]
    return out


def _lerp_half(vals: list[float], n: int) -> list[float]:
    out = []
    for i in range(n):
        t = i / (n - 1) * (len(vals) - 1)
        k = int(t)
        f = t - k
        out.append(vals[k] * (1 - f) + vals[min(k + 1, len(vals) - 1)] * f)
    return out


def outline_from_spine(spine: list[tuple[float, float]], half: list[float]) -> OpsPath:
    dense = _resample_chain(spine, 24)
    hs = _lerp_half(half, 24)
    samples = sample_polyline([Vec2(x, y) for x, y in dense], n_per_seg=1)
    if len(samples) != len(hs):
        hs = _lerp_half(half, len(samples))
    return _poly_path(variable_width_outline(samples, hs, close=True))


def outline_from_sides(
    outer: list[tuple[float, float]],
    inner: list[tuple[float, float]],
    k: int | None = None,
) -> OpsPath:
    """左右を弧長で間引き、対称オフセットせず輪郭にする。"""
    k = HARA_SPINE_K if k is None else k
    ra = _resample_chain(outer, k)
    rb = _resample_chain(inner, k)
    return _poly_path([Vec2(*p) for p in ra] + [Vec2(*p) for p in reversed(rb)])


def _ring_bounds(ring: list[tuple[float, float]]) -> list[float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def _overlap(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    aa = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / aa


def split_hara_pair(ring: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """人・入: 縦中線の交差で左右の輪郭に分ける。"""
    pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    n = len(pts)
    if n < 16:
        return [ring]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx = 0.5 * (min(xs) + max(xs))
    ymin, ymax = min(ys), max(ys)
    crossings = []
    for i in range(n):
        x0, x1 = pts[i][0], pts[(i + 1) % n][0]
        if (x0 - mx) * (x1 - mx) <= 0 and x0 != x1:
            t = (mx - x0) / (x1 - x0)
            y = pts[i][1] + t * (pts[(i + 1) % n][1] - pts[i][1])
            crossings.append((i, y))
    crossings.sort(key=lambda c: -c[1])
    i_t = max(range(n), key=lambda i: pts[i][1])
    low = [i for i, p in enumerate(pts) if p[1] < ymin + 0.28 * (ymax - ymin)]
    if not low:
        return [ring]
    i_l = min(low, key=lambda i: pts[i][0])
    i_r = max(low, key=lambda i: pts[i][0])
    crotch = None
    for i, y in crossings:
        if y < pts[i_t][1] - 0.15 * (ymax - ymin):
            crotch = i
            break
    if crotch is None:
        crotch = crossings[1][0] if len(crossings) > 1 else i_t

    def seg(a: int, b: int) -> list[tuple[float, float]]:
        out = []
        i = a
        while True:
            out.append(pts[i])
            if i == b:
                break
            i = (i + 1) % n
            if len(out) > n:
                break
        return out

    def includes(a: int, b: int, idx: int) -> bool:
        i = a
        for _ in range(n):
            if i == idx:
                return True
            if i == b:
                return False
            i = (i + 1) % n
        return False

    def side(tip: int, avoid: int) -> list[tuple[float, float]]:
        if includes(tip, i_t, avoid):
            outer = list(reversed(seg(i_t, tip)))
        else:
            outer = seg(tip, i_t)
        if includes(tip, crotch, avoid):
            inner = list(reversed(seg(crotch, tip)))
        else:
            inner = seg(tip, crotch)
        return outer + list(reversed(inner))

    return [side(i_l, i_r), side(i_r, i_l)]


def split_hara_pair_chains(
    ring: list[tuple[float, float]],
) -> list[tuple[list[tuple[float, float]], list[tuple[float, float]]]]:
    """人: 分割した外側／内側を _split_sides でやり直さない。内側の先に頂点を足す。"""
    pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    n = len(pts)
    if n < 16:
        return []
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx = 0.5 * (min(xs) + max(xs))
    ymin, ymax = min(ys), max(ys)
    crossings = []
    for i in range(n):
        x0, x1 = pts[i][0], pts[(i + 1) % n][0]
        if (x0 - mx) * (x1 - mx) <= 0 and x0 != x1:
            t = (mx - x0) / (x1 - x0)
            y = pts[i][1] + t * (pts[(i + 1) % n][1] - pts[i][1])
            crossings.append((i, y))
    crossings.sort(key=lambda c: -c[1])
    i_t = max(range(n), key=lambda i: pts[i][1])
    low = [i for i, p in enumerate(pts) if p[1] < ymin + 0.28 * (ymax - ymin)]
    if not low or not crossings:
        return []
    i_l = min(low, key=lambda i: pts[i][0])
    i_r = max(low, key=lambda i: pts[i][0])
    crotch = None
    for i, y in crossings:
        if y < pts[i_t][1] - 0.15 * (ymax - ymin):
            crotch = i
            break
    if crotch is None:
        crotch = crossings[1][0] if len(crossings) > 1 else i_t

    def seg(a: int, b: int) -> list[tuple[float, float]]:
        out = []
        i = a
        while True:
            out.append(pts[i])
            if i == b:
                break
            i = (i + 1) % n
            if len(out) > n:
                break
        return out

    def includes(a: int, b: int, idx: int) -> bool:
        i = a
        for _ in range(n):
            if i == idx:
                return True
            if i == b:
                return False
            i = (i + 1) % n
        return False

    def chains(tip: int, avoid: int):
        outer = list(reversed(seg(i_t, tip))) if includes(tip, i_t, avoid) else seg(tip, i_t)
        inner = list(reversed(seg(crotch, tip))) if includes(tip, crotch, avoid) else seg(tip, crotch)
        if math.hypot(outer[0][0] - pts[tip][0], outer[0][1] - pts[tip][1]) > math.hypot(
            outer[-1][0] - pts[tip][0], outer[-1][1] - pts[tip][1]
        ):
            outer = list(reversed(outer))
        if math.hypot(inner[0][0] - pts[tip][0], inner[0][1] - pts[tip][1]) > math.hypot(
            inner[-1][0] - pts[tip][0], inner[-1][1] - pts[tip][1]
        ):
            inner = list(reversed(inner))
        apex = pts[i_t]
        if math.hypot(inner[-1][0] - apex[0], inner[-1][1] - apex[1]) > 2:
            inner = inner + [apex]
        return outer, inner

    return [chains(i_l, i_r), chains(i_r, i_l)]


def fit_hara_spine_from_sides(
    outer: list[tuple[float, float]],
    inner: list[tuple[float, float]],
    k: int = HARA_SPINE_K,
):
    if len(outer) < 2 or len(inner) < 2:
        return None
    origin = outer[0]
    axis = (outer[-1][0] - outer[0][0], outer[-1][1] - outer[0][1])
    n = max(24, k * 3)
    ra = _resample_by_proj(outer, origin, axis, n)
    rb = _resample_by_proj(inner, origin, axis, n)
    spine = [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for p, q in zip(ra, rb)]
    half = [0.5 * math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(ra, rb)]
    idxs = [round(i * (len(spine) - 1) / (k - 1)) for i in range(k)]
    return [spine[i] for i in idxs], [half[i] for i in idxs]


def _boxes_intersect(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def clip_ring_below(ring: list[tuple[float, float]], y: float) -> list[list[tuple[float, float]]]:
    """屋根ステムより下だけ残す。入の左画から水平の屋根を外す。"""
    b = _ring_bounds(ring)
    rp = OpsPath()
    pen = rp.getPen()
    pen.moveTo(ring[0])
    for p in ring[1:]:
        pen.lineTo(p)
    pen.closePath()
    box = OpsPath()
    q = box.getPen()
    q.moveTo((b[0] - 20, b[1] - 20))
    q.lineTo((b[2] + 20, b[1] - 20))
    q.lineTo((b[2] + 20, y))
    q.lineTo((b[0] - 20, y))
    q.closePath()
    out = OpsPath()
    intersection([rp], [box], out.getPen(), fix_winding=True)
    return [r for r in _ops_rings(out) if len(r) >= 8]


def roof_stem(stems: list[dict], face: list[float]) -> dict | None:
    hs = [s for s in stems if s["kind"] == "h"]
    if not hs:
        return None
    top = max(hs, key=lambda s: s["y1"])
    if top["y0"] < face[1] + 0.7 * (face[3] - face[1]):
        return None
    return top


def extend_roof_to_apex(stems: list[dict], ring: list[tuple[float, float]]) -> list[dict]:
    """入: 屋根横画の右端が頂点より短い。頂点の X まで伸ばす。"""
    roof = roof_stem(stems, _ring_bounds(ring))
    if roof is None:
        return stems
    apex = max(ring, key=lambda p: p[1])
    if apex[0] <= roof["x1"] + 1:
        return stems
    out = []
    for s in stems:
        s = dict(s)
        if (
            s["kind"] == "h"
            and abs(s["y0"] - roof["y0"]) <= 1
            and abs(s["y1"] - roof["y1"]) <= 1
        ):
            s["x1_paired"] = s["x1"]
            s["x1"] = round(float(apex[0]), 2)
            s["length"] = round(s["x1"] - s["x0"], 2)
        out.append(s)
    return out


def roof_shoulder_poly(roof: dict, apex: tuple[float, float]) -> list[Vec2] | None:
    """伸ばした屋根の上に、頂点まで上がる直角三角形を載せる。"""
    hinge = roof.get("x1_paired", roof["x1"])
    if apex[1] <= roof["y1"] + 8 or apex[0] <= hinge + 1:
        return None
    return [
        Vec2(hinge, roof["y1"]),
        Vec2(apex[0], roof["y1"]),
        Vec2(apex[0], apex[1]),
    ]


def split_hara_pair_with_roof(
    ring: list[tuple[float, float]],
    stems: list[dict],
) -> list[list[tuple[float, float]]]:
    parts = split_hara_pair(ring)
    roof = roof_stem(stems, _ring_bounds(ring))
    if roof is None:
        return parts
    sb = [roof["x0"], roof["y0"], roof["x1"], roof["y1"]]
    out: list[list[tuple[float, float]]] = []
    for part in parts:
        if _boxes_intersect(_ring_bounds(part), sb):
            clipped = clip_ring_below(part, roof["y0"])
            out.extend(clipped if clipped else [part])
        else:
            out.append(part)
    return out


def hara_paths_from_residual(
    term: dict,
    rings: list[list[tuple[float, float]]],
    *,
    split_pair: bool = False,
    upm: float = 2048.0,
    exact_rings: list[list[tuple[float, float]]] | None = None,
    stems: list[dict] | None = None,
) -> list[OpsPath]:
    role = term.get("role")
    b = term["bounds"]
    matched = [r for r in rings if _overlap(_ring_bounds(r), b) > 0.45]
    if role == "hara_pair" and split_pair:
        src = max(exact_rings, key=len) if exact_rings else (matched[0] if len(matched) == 1 else None)
        if src is not None:
            if roof_stem(stems or [], _ring_bounds(src)) is None:
                paths = []
                for outer, inner in split_hara_pair_chains(src):
                    if len(outer) >= 2 and len(inner) >= 2:
                        paths.append(outline_from_sides(outer, inner))
                if paths:
                    return paths
            matched = split_hara_pair_with_roof(src, stems or [])
    paths = []
    for ring in matched:
        paths.extend(paths_from_hara_ring(ring, upm))
    return paths


def _ten_poly(bounds: list[float]) -> list[Vec2]:
    x0, y0, x1, y1 = bounds
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    return [
        Vec2(x0 + 0.08 * w, y1),
        Vec2(x1, y0 + 0.55 * h),
        Vec2(x1 - 0.12 * w, y0),
        Vec2(x0, y0 + 0.35 * h),
    ]


def template_paths(term: dict, stems: list[dict]) -> list[OpsPath]:
    role = term.get("role") or term["kind"]
    b = term["bounds"]
    hs = [s for s in stems if s["kind"] == "h"]
    vs = [s for s in stems if s["kind"] == "v"]
    if role == "box_uroko":
        stem = _nearest_stem(term, hs) if hs else None
        vstem = _nearest_stem(term, vs) if vs else None
        if stem and vstem:
            return [_poly_path(_box_uroko_poly(stem, vstem))]
        if stem is None:
            return []
        return [_poly_path(_uroko_poly(stem, b))]
    if role in ("bar_uroko", "uroko"):
        stem = _nearest_stem(term, hs) if hs else None
        if stem is None:
            return []
        return [_poly_path(_uroko_poly(stem, b))]
    if role == "top_cap":
        stem = _nearest_stem(term, vs) if vs else _nearest_stem(term, stems, "v")
        if stem is None:
            return []
        return [_poly_path(_top_cap_poly(stem, b))]
    if role == "uchikomi":
        vstem = _nearest_stem(term, vs) if vs else None
        hstem = _nearest_stem(term, hs) if hs else None
        if vstem is not None and hstem is not None and b[1] >= hstem["y1"] - 8:
            return [_poly_path(_top_left_cap(vstem, hstem))]
        if vstem is not None and b[1] >= vstem["y1"] - 8:
            return [_poly_path(_top_cap_poly(vstem, b))]
        if hstem is None:
            return []
        return [rect_path(min(b[0], hstem["x0"]), hstem["y0"], hstem["x0"], hstem["y1"])]
    if role == "left_hara":
        return [_poly_path(_hara_band(b, left=True))]
    if role == "right_hara":
        return [_poly_path(_hara_band(b, left=False))]
    if role == "hara_pair":
        return [_poly_path(p) for p in _hara_pair_polys(b)]
    if role == "ten":
        return [_poly_path(_ten_poly(b))]
    return []


def _ring_is_wide(ring: list[tuple[float, float]], upm: float) -> bool:
    b = _ring_bounds(ring)
    return (b[2] - b[0]) > 0.3 * upm or (b[3] - b[1]) > 0.25 * upm


def leftover_side_paths(
    term: dict,
    rings: list[list[tuple[float, float]]],
    upm: float,
) -> list[OpsPath]:
    """端物残差は左右輪郭。三角うろこより残差の形に近い。"""
    matched = [r for r in rings if _overlap(_ring_bounds(r), term["bounds"]) > 0.45]
    paths: list[OpsPath] = []
    for ring in matched:
        got = paths_from_hara_ring(ring, upm)
        if got:
            paths.extend(got)
            continue
        sides = _split_sides(ring)
        if sides is not None:
            paths.append(outline_from_sides(*sides))
            continue
        pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
        if len(pts) >= 3:
            paths.append(_poly_path([Vec2(*p) for p in pts]))
    return paths


def top_cap_paths(
    term: dict,
    rings: list[list[tuple[float, float]]],
    stems: list[dict],
    upm: float,
) -> tuple[list[OpsPath], str]:
    """狭い天は三角キャップ。手の広い折れは左右輪郭。"""
    matched = [r for r in rings if _overlap(_ring_bounds(r), term["bounds"]) > 0.45]
    wide = [r for r in matched if (_ring_bounds(r)[2] - _ring_bounds(r)[0]) > 0.3 * upm]
    if wide:
        paths = []
        for ring in wide:
            sides = _split_sides(ring)
            if sides is not None:
                paths.append(outline_from_sides(*sides))
        if paths:
            return paths, "top_hook"
    return template_paths(term, stems), "top_cap"


def stems_path(stems: list[dict]) -> OpsPath:
    paths = [rect_path(s["x0"], s["y0"], s["x1"], s["y1"]) for s in stems]
    return combine(paths, union) if paths else OpsPath()


def vector_iou(exact: OpsPath, rebuilt: OpsPath) -> tuple[float, float]:
    err = OpsPath()
    xor([exact], [rebuilt], err.getPen(), fix_winding=True)
    xor_area = abs(err.area)
    a = abs(exact.area) or 1.0
    b = abs(rebuilt.area) or 1.0
    inter = max(0.0, 0.5 * (a + b - xor_area))
    union_a = a + b - inter
    return (inter / union_a if union_a else 0.0), xor_area


def path_to_pen(path: OpsPath, pen) -> None:
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            pen.moveTo(pts[0])
        elif verb == PathVerb.LINE:
            pen.lineTo(pts[0])
        elif verb == PathVerb.QUAD:
            pen.qCurveTo(pts[0], pts[1])
        elif verb == PathVerb.CUBIC:
            pen.curveTo(pts[0], pts[1], pts[2])
        elif verb == PathVerb.CLOSE:
            pen.closePath()


def write_rebuild_ttf(rows: list[dict], dest: Path) -> None:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    dest = assert_throwaway(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    upm = int(rows[0]["upm"])
    order = [".notdef"] + [uniname(r["char"]) for r in rows]
    cmap = {ord(r["char"]): uniname(r["char"]) for r in rows}
    glyf = {}
    metrics = {}
    nd = TTGlyphPen(None)
    glyf[".notdef"] = nd.glyph()
    metrics[".notdef"] = (upm, 0)
    for r in rows:
        pen = TTGlyphPen(None)
        path_to_pen(r["_path"], pen)
        name = uniname(r["char"])
        glyf[name] = pen.glyph()
        b = r["_path"].bounds
        lsb = int(round(b[0])) if b else 0
        metrics[name] = (int(r["width"]), lsb)
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=int(upm * 0.88), descent=-int(upm * 0.12))
    fb.setupMaxp()
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "MyMinchoRebuild", "styleName": "Regular"})
    fb.save(dest)


def rebuild_row(row: dict) -> dict:
    from extract_ref_elements import glyph_recording, recording_to_path

    rec, _, _, _ = glyph_recording(Path(row["_ref"]), row["char"])
    exact = recording_to_path(rec)
    junctions = [t for t in row["terminals"] if _is_junction(t, row, exact)]
    real = [t for t in row["terminals"] if not _is_junction(t, row, exact)]
    merged = fill_corners(absorb_junctions(merge_collinear(row["stems"]), junctions))
    merged, real = absorb_extensions(merged, real, exact)
    merged = merge_collinear(close_open_junctions(merged, exact))
    exact_rings = _ops_rings(exact)
    # 穴がある字（又）を入の屋根にしない。
    split_pair = (
        row.get("n_outer") == 1
        and len(row.get("stems") or []) <= 1
        and row.get("n_counter", 0) == 0
    )
    if split_pair and exact_rings:
        merged = extend_roof_to_apex(merged, max(exact_rings, key=len))
    stem_only = stems_path(merged)
    residual = OpsPath()
    if merged:
        difference([exact], [stem_only], residual.getPen(), fix_winding=True)
    else:
        residual = exact
    # 端物・はらいの残差は二次を潰さない。折れ線化は分割・くびれの解析だけ。
    used = []
    for t in real:
        role = t.get("role") or t["kind"]
        used.append("uchikomi" if role == "junction" else role)
    if split_pair and exact_rings:
        roof = roof_stem(merged, _ring_bounds(max(exact_rings, key=len)))
        if roof is not None:
            apex = max(max(exact_rings, key=len), key=lambda p: p[1])
            if roof_shoulder_poly(roof, apex) is not None:
                used.append("roof_shoulder")
    rebuilt = combine([stem_only, residual], union) if merged else residual
    iou_stems, xor_stems = vector_iou(exact, stem_only)
    iou_tmpl, xor_tmpl = vector_iou(exact, rebuilt)
    return {
        "char": row["char"],
        "unicode": row["unicode"],
        "upm": row["upm"],
        "width": row["width"],
        "stems_merged": merged,
        "junctions": len(junctions),
        "templates": used,
        "vector_iou_stems": round(iou_stems, 4),
        "vector_iou_templates": round(iou_tmpl, 4),
        "xor_stems": round(xor_stems, 1),
        "xor_templates": round(xor_tmpl, 1),
        "_path": rebuilt,
        "_stem_path": stem_only,
        "_exact": exact,
    }


def sheet(pairs, dest: Path) -> None:
    from PIL import Image, ImageDraw

    cell = 200
    pad = 8
    rows = len(pairs)
    page = Image.new("RGB", (cell * 4 + pad * 5, rows * (cell + 28) + pad), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    labels = ("exact", "stems", "templates", "xor")
    for i, (ch, exact, stems, tmpl, score) in enumerate(pairs):
        y = pad + i * (cell + 28)
        imgs = [
            Image.fromarray((~exact).astype(np.uint8) * 255).convert("RGB"),
            Image.fromarray((~stems).astype(np.uint8) * 255).convert("RGB"),
            Image.fromarray((~tmpl).astype(np.uint8) * 255).convert("RGB"),
        ]
        xor_im = np.zeros((cell, cell, 3), dtype=np.uint8)
        xor_im[:] = 255
        xor_im[np.logical_xor(exact, tmpl)] = (220, 0, 0)
        imgs.append(Image.fromarray(xor_im))
        for j, im in enumerate(imgs):
            page.paste(im, (pad * (j + 1) + cell * j, y))
        draw.text((pad, y + cell + 2), f"{ch} IoU {score:.4f}  " + " / ".join(labels), fill=(0, 0, 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.save(dest)


def write_md(rows: list[dict], dest: Path) -> None:
    lines = [
        "# ステム＋端物テンプレ再構成",
        "",
        "開いた接合を閉じ、打ち込みは三角で戻す。はらいと端物の残差は二次を潰さない。正本は書いていない。",
        "",
        "| 字 | stems IoU | templates IoU | 画素 IoU | 接合 | テンプレ |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        kinds = ",".join(r["templates"]) if r["templates"] else "—"
        pix = r.get("pixel_iou")
        pix_s = f"{pix:.3f}" if pix is not None else "—"
        lines.append(
            f"| {r['char']} | {r['vector_iou_stems']:.3f} | {r['vector_iou_templates']:.3f} | "
            f"{pix_s} | {r['junctions']} | {kinds} |"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild from stems + terminal templates")
    ap.add_argument("--ref", type=Path, default=REF_DEFAULT)
    ap.add_argument(
        "--chars",
        default="十二三口日田中永八人入木本大天又文火矢川水手上土王玉力刀月用小心少耳言古石見雨食国車金風東花",
    )
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if not args.ref.is_file():
        print(f"error: missing {args.ref}", file=sys.stderr)
        return 2
    scratch = assert_throwaway(SCRATCH)
    scratch.mkdir(parents=True, exist_ok=True)
    extracted = []
    for ch in args.chars:
        row = extract_char(args.ref, ch)
        row["_ref"] = str(args.ref)
        extracted.append(row)
    rebuilt = [rebuild_row(r) for r in extracted]
    ttf = scratch / "rebuild.ttf"
    write_rebuild_ttf(rebuilt, ttf)
    stem_rows = []
    for r in rebuilt:
        copy = dict(r)
        copy["_path"] = r["_stem_path"]
        stem_rows.append(copy)
    stem_ttf = scratch / "rebuild_stems.ttf"
    write_rebuild_ttf(stem_rows, stem_ttf)
    pairs = []
    for r in rebuilt:
        ref_c = render_em(args.ref, r["char"])
        stem_c = render_em(stem_ttf, r["char"])
        tmpl_c = render_em(ttf, r["char"])
        pix = iou(ref_c >= INK, tmpl_c >= INK)
        r["pixel_iou"] = round(pix, 6)
        pairs.append((r["char"], pack_bbox(ref_c), pack_bbox(stem_c), pack_bbox(tmpl_c), pix))
        print(
            f"{r['char']} stems={r['vector_iou_stems']:.3f} tmpl={r['vector_iou_templates']:.3f} "
            f"px={pix:.4f} terms={r['templates']}"
        )
    png = args.out / "rebuild_compare.png"
    sheet(pairs, png)
    payload = {
        "ref": str(args.ref),
        "shipping_ufo_written": False,
        "method": "stems-plus-templates",
        "uroko_family": {
            "bottom_frac": UROKO_BOTTOM_FRAC,
            "tip_y_frac": UROKO_TIP_Y_FRAC,
            "peak_x_frac": UROKO_PEAK_X_FRAC,
        },
        "glyphs": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rebuilt],
        "mean_vector_iou_templates": round(
            float(np.mean([r["vector_iou_templates"] for r in rebuilt])), 4
        ),
        "mean_pixel_iou": round(float(np.mean([r["pixel_iou"] for r in rebuilt])), 6),
        "png": str(png),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "rebuild.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_md(rebuilt, args.out / "rebuild.md")
    print(f"mean tmpl IoU={payload['mean_vector_iou_templates']} px={payload['mean_pixel_iou']} {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
