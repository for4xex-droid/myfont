"""クラシックとシックの S。腕は天地の線に沿い、くちばしは腕の端から字の内側へ垂れる。"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from engine.geometry import Vec2
from engine.latin.build import _centerline, _fit_bowls, build_glyph
from engine.latin.load import load_resolved
from engine.latin.outline import fit_outline
from engine.latin.schema import free_scalar_count

_BEAK = ("classic", "chic")
_DROP = {"classic": 0.20, "chic": 0.27}


def _ring(contour):
    pts = list(contour)
    if len(pts) > 1 and (pts[0] - pts[-1]).length() < 1e-6:
        pts = pts[:-1]
    return pts


def _turn(prev, point, nxt) -> float:
    d1, d2 = point - prev, nxt - point
    if d1.length() < 0.4 or d2.length() < 0.4:
        return 0.0
    return abs(math.degrees(math.atan2(d1.cross(d2), d1.dot(d2))))


def _vertical_faces(points):
    """x が動かない 40 UPM より長い縦の辺。"""
    out = []
    for start, end in pairwise([*points, points[0]]):
        if abs(start.x - end.x) <= 0.5 and abs(start.y - end.y) > 40.0:
            out.append((start.x, min(start.y, end.y), max(start.y, end.y)))
    return out


def _arms(resolved):
    """上の端と下の端で、腕の外縁と内縁の y。"""
    stroke = resolved.skeleton.strokes[0]
    frames, _shrink = _fit_bowls(resolved)
    samples, widths = _centerline(stroke, resolved, frames.get(stroke.id), hug=False)
    out = []
    for index, top in ((0, True), (len(samples) - 1, False)):
        origin, tangent = samples[index]
        normal = tangent.perpendicular().normalized()
        a = origin + normal * widths[index]
        b = origin - normal * widths[index]
        outer, inner = (a, b) if (a.y > b.y) == top else (b, a)
        out.append({"top": top, "outer": outer, "inner": inner, "origin": origin})
    return out, samples, widths


def _beaks(style):
    resolved = load_resolved("S", style)
    outline = build_glyph(resolved)
    points = _ring(outline.contours[0])
    arms, samples, widths = _arms(resolved)
    faces = _vertical_faces(points)
    xs = [p.x for p in points]
    found = []
    for arm in arms:
        # 縦の面はくちばしの外の面。上の端なら右、下の端なら左の、いちばん外の縦の辺。
        side = [f for f in faces if (f[2] > 350.0) == arm["top"]]
        assert side, (
            f"{style}: no vertical face at the {'top' if arm['top'] else 'bottom'} end"
        )
        face = (
            max(side, key=lambda f: f[0])
            if arm["top"]
            else min(side, key=lambda f: f[0])
        )
        tip_y = face[1] if arm["top"] else face[2]
        rim_y = face[2] if arm["top"] else face[1]
        found.append(
            {
                **arm,
                "face": face,
                "tip_y": tip_y,
                "rim_y": rim_y,
                "drop": face[2] - face[1],
                "points": points,
                "width": max(xs) - min(xs),
                "x0": min(xs),
            }
        )
    return resolved, found, samples, widths


def _corner_ok(point, beak, reach):
    """くちばしの角は、縦の面の上端と下端の高さの線の上にある。"""
    x = beak["face"][0]
    near_x = abs(point.x - x) <= reach
    return near_x and (
        abs(point.y - beak["tip_y"]) <= 3.0 or abs(point.y - beak["rim_y"]) <= 3.0
    )


def _resample(points, step):
    out = [points[0]]
    carry = 0.0
    for a, b in pairwise([*points, points[0]]):
        seg = (b - a).length()
        pos = step - carry
        while pos <= seg:
            out.append(a + (b - a) * (pos / seg))
            pos += step
        carry = seg - (pos - step)
    return out[:-1] if (out[-1] - out[0]).length() < step * 0.5 else out


def _curvature(points, step=2.0, k=4, window=4):
    q = _resample(points, step)
    m = len(q)
    raw = []
    for i in range(m):
        a = q[i] - q[i - k]
        b = q[(i + k) % m] - q[i]
        raw.append(math.atan2(a.cross(b), a.dot(b)) / (k * step))
    smooth = [
        sum(raw[(i + j) % m] for j in range(-window, window + 1)) / (2 * window + 1)
        for i in range(m)
    ]
    return q, smooth


def _sharp(points, deg=25.0):
    out = []
    for i, p in enumerate(points):
        if _turn(points[i - 1], p, points[(i + 1) % len(points)]) > deg:
            out.append(p)
    return out


def _knee_and_inflections(points, clear=14.0):
    """20 UPM 進む間の曲率の変わり方の最大と、角から clear より近い所を除いた変曲点の数。"""
    corners = _sharp(points)
    q, kappa = _curvature(points)
    m = len(q)
    near = [any((q[i] - c).length() < clear for c in corners) for i in range(m)]
    knee = 0.0
    for i in range(m):
        if near[i] or near[(i + 5) % m] or near[i - 5]:
            continue
        knee = max(knee, abs(kappa[(i + 5) % m] - kappa[i - 5]))
    flips = 0
    last = 0
    for i in range(m):
        if near[i]:
            last = 0
            continue
        sign = 1 if kappa[i] > 0.0004 else -1 if kappa[i] < -0.0004 else 0
        if sign and last and sign != last:
            flips += 1
        if sign:
            last = sign
    return knee, flips


def _flatten(path, steps=60):
    cur = Vec2(*path.start)
    out = [cur]
    for seg in path.segs:
        if seg[0] == "L":
            cur = Vec2(float(seg[1]), float(seg[2]))
            out.append(cur)
            continue
        p1 = Vec2(float(seg[1]), float(seg[2]))
        p2 = Vec2(float(seg[3]), float(seg[4]))
        p3 = Vec2(float(seg[5]), float(seg[6]))
        for i in range(1, steps + 1):
            t = i / steps
            u = 1.0 - t
            out.append(
                cur * (u**3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t**3)
            )
        cur = p3
    return _ring(out)


@pytest.mark.parametrize("style", _BEAK)
def test_variants_have_seven_knots(style):
    resolved = load_resolved("S", style)
    assert len(resolved.skeleton.strokes[0].knots) == 7
    assert free_scalar_count(resolved.skeleton) <= 12


@pytest.mark.parametrize("style", _BEAK)
def test_arms_lie_on_the_cap_and_base_lines(style):
    resolved = load_resolved("S", style)
    cap = resolved.style.cap_height
    (top, bottom), _samples, _widths = _arms(resolved)
    assert top["outer"].y >= 0.98 * cap
    assert bottom["outer"].y <= 0.02 * cap


@pytest.mark.parametrize("style", _BEAK)
def test_beak_hangs_inward_from_the_arm_end(style):
    resolved, beaks, _samples, _widths = _beaks(style)
    cap = resolved.style.cap_height
    for beak in beaks:
        # 上端（下の端では下端）は腕の外縁にそろい、0.01 キャップより外へ出さない
        assert abs(beak["rim_y"] - beak["outer"].y) <= 0.01 * cap
        # 縦の面は腕の外縁から字の内側へ垂れる
        if beak["top"]:
            assert beak["tip_y"] < beak["outer"].y
        else:
            assert beak["tip_y"] > beak["outer"].y
        x = beak["face"][0]
        beyond = [
            p
            for p in beak["points"]
            if (p.x > x + 0.5 if beak["top"] else p.x < x - 0.5)
        ]
        if beak["top"]:
            assert all(p.y < 0.6 * cap for p in beyond)
        else:
            assert all(p.y > 0.4 * cap for p in beyond)


@pytest.mark.parametrize("style", _BEAK)
def test_beak_drop_is_the_style_value(style):
    resolved, beaks, _samples, _widths = _beaks(style)
    cap = resolved.style.cap_height
    assert resolved.style.metrics["beak_drop"] == pytest.approx(_DROP[style])
    for beak in beaks:
        assert 0.16 * cap <= beak["drop"] <= 0.30 * cap
        assert beak["drop"] == pytest.approx(_DROP[style] * cap, abs=2.0)


@pytest.mark.parametrize("style", _BEAK)
def test_beak_is_not_a_stump(style):
    """くちばしは腕の内縁より先へ、セリフの厚さの 2 倍以上出る。"""
    resolved, beaks, _samples, _widths = _beaks(style)
    thick = resolved.style.metrics["serif_thick"] * resolved.style.cap_height
    for beak in beaks:
        past = abs(beak["inner"].y - beak["tip_y"])
        assert past >= 2.0 * thick


@pytest.mark.parametrize("style", _BEAK)
def test_crowns_sit_in_the_middle(style):
    _resolved, beaks, _samples, _widths = _beaks(style)
    points = beaks[0]["points"]
    x0, width = beaks[0]["x0"], beaks[0]["width"]
    top = max(points, key=lambda p: p.y)
    bottom = min(points, key=lambda p: p.y)
    for point in (top, bottom):
        assert 0.40 <= (point.x - x0) / width <= 0.60


@pytest.mark.parametrize("style", _BEAK)
def test_only_the_beak_has_corners(style):
    resolved, beaks, _samples, _widths = _beaks(style)
    cap = resolved.style.cap_height
    reach = 0.10 * cap
    points = beaks[0]["points"]
    for index, point in enumerate(points):
        turn = _turn(points[index - 1], point, points[(index + 1) % len(points)])
        if turn <= 15.0:
            continue
        assert any(_corner_ok(point, beak, reach) for beak in beaks), (
            f"{style}: fold {turn:.1f} at ({point.x:.1f}, {point.y:.1f})"
        )


def test_classic_beak_bracket_bends_softly():
    resolved, beaks, _samples, _widths = _beaks("classic")
    cap = resolved.style.cap_height
    reach = resolved.style.metrics["beak_bracket"] * cap
    assert reach == pytest.approx(45.0, abs=0.1)
    for beak in beaks:
        x = beak["face"][0]
        lo, hi = sorted((beak["tip_y"], beak["rim_y"]))
        seen = 0
        points = beak["points"]
        for index, point in enumerate(points):
            if abs(point.x - x) > reach + 40.0 or not lo + 3.0 < point.y < hi - 3.0:
                continue
            if abs(point.x - x) < 0.5:
                continue
            turn = _turn(points[index - 1], point, points[(index + 1) % len(points)])
            assert turn <= 5.0, f"({point.x:.1f}, {point.y:.1f}) turn {turn:.1f}"
            seen += 1
        assert seen > 8


def test_chic_beak_sweeps_out_of_the_arm():
    """内の面は腕の内縁から接線を切らさずに入り、先の角まで曲線で続く。"""
    resolved, beaks, _samples, _widths = _beaks("chic")
    cap = resolved.style.cap_height
    tip = resolved.style.metrics["beak_tip"] * cap
    for beak in beaks:
        x = beak["face"][0]
        lo, hi = sorted((beak["tip_y"], beak["rim_y"]))
        points = beak["points"]
        seen = 0
        for index, point in enumerate(points):
            if abs(point.x - x) < 0.5 or abs(point.x - x) > 0.25 * cap:
                continue
            if not lo + 3.0 < point.y < hi - 3.0:
                continue
            turn = _turn(points[index - 1], point, points[(index + 1) % len(points)])
            assert turn <= 8.0, f"({point.x:.1f}, {point.y:.1f}) turn {turn:.1f}"
            seen += 1
        assert seen > 16
        # 先の幅
        at_tip = [
            p for p in points if abs(p.y - beak["tip_y"]) < 0.5 and abs(p.x - x) > 0.5
        ]
        assert at_tip
        assert min(abs(p.x - x) for p in at_tip) == pytest.approx(tip, abs=1.0)


def test_chic_arm_stays_a_hairline():
    resolved = load_resolved("S", "chic")
    cap = resolved.style.cap_height
    _, samples, widths = _arms(resolved)
    crown = max(range(len(samples)), key=lambda i: samples[i][0].y)
    assert (
        max(2.0 * widths[i] for i in range(crown + 1))
        <= 2.5 * resolved.pen.hairline * cap
    )


def test_chic_spine_is_as_thick_as_the_stem():
    resolved = load_resolved("S", "chic")
    stem = resolved.pen.stem * resolved.style.cap_height / 2.0
    _, samples, widths = _arms(resolved)
    xs = [tangent.x for _pos, tangent in samples]
    start = next(i for i in range(1, len(xs)) if xs[i - 1] < 0 <= xs[i])
    end = next(i for i in range(start + 1, len(xs)) if xs[i - 1] > 0 >= xs[i])
    mid = (start + end) // 2
    assert widths[mid] >= stem - 0.5


def test_chic_outline_has_no_bumps():
    """曲率の変わり方（膝）は参照の Bodoni（0.004）に近く、変曲点は背の2つとつなぎの2つまで。"""
    resolved = load_resolved("S", "chic")
    outline = build_glyph(resolved)
    knee, flips = _knee_and_inflections(_ring(outline.contours[0]))
    assert knee <= 0.006
    assert flips <= 4


def test_chic_font_outline_has_no_bumps():
    resolved = load_resolved("S", "chic")
    paths = fit_outline(build_glyph(resolved), resolved.style)
    main = max(paths, key=lambda p: len(p.segs))
    knee, flips = _knee_and_inflections(_flatten(main))
    assert knee <= 0.006
    assert flips <= 4


def test_classic_counters_have_no_step():
    """最細の向きが碗の急な曲がりに来るので、太さを弧の長さで均さないと内側に段が出る（膝 0.022）。
    くちばしのブラケットは設計の曲がりなので、角から 100 UPM は見ない。"""
    resolved = load_resolved("S", "classic")
    outline = build_glyph(resolved)
    knee, _flips = _knee_and_inflections(_ring(outline.contours[0]), clear=100.0)
    assert knee <= 0.011
    paths = fit_outline(outline, resolved.style)
    main = max(paths, key=lambda p: len(p.segs))
    knee, _flips = _knee_and_inflections(_flatten(main), clear=100.0)
    assert knee <= 0.011


def test_modern_s_keeps_a_steep_flat_end_and_pop_stays_round():
    modern = load_resolved("S", "modern")
    pop = load_resolved("S", "pop")
    assert modern.style.terminals["open"] == "flat"
    assert pop.style.terminals["open"] == "round"
    samples, _widths = _centerline(modern.skeleton.strokes[0], modern, hug=False)
    for index in (0, -1):
        _origin, tangent = samples[index]
        deg = abs(math.degrees(math.atan2(tangent.y, tangent.x))) % 180.0
        assert min(deg, 180.0 - deg) > 60.0


@pytest.mark.parametrize("style", _BEAK)
def test_round_end_stays_a_ball(style):
    assert load_resolved("S", style).style.terminals["round_end"] == "ball"
    assert load_resolved("S", style).style.terminals["open"] == "beak"
