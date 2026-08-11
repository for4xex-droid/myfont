"""折れ線 → cubic 列フィット（Phase 1 / Schneider 系最小二乗）。

GPL 実装は参照しない。Graphics Gems の公開アルゴリズムに基づく純実装。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

Point = tuple[float, float]
SegKind = Literal["L", "C"]


@dataclass
class ContourPath:
    """閉輪郭のセグメント列。start から始まり、最後の点が start に戻る想定。"""

    start: Point
    segs: list[tuple] = field(default_factory=list)
    # ("L", x, y) or ("C", c1x, c1y, c2x, c2y, x, y)

    def on_curve_points(self) -> list[Point]:
        pts = [self.start]
        for seg in self.segs:
            if seg[0] == "L":
                pts.append((float(seg[1]), float(seg[2])))
            else:
                pts.append((float(seg[5]), float(seg[6])))
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return pts

    def transform(self, fn) -> ContourPath:
        def tp(x: float, y: float) -> Point:
            return fn(x, y)

        start = tp(*self.start)
        segs: list[tuple] = []
        for seg in self.segs:
            if seg[0] == "L":
                x, y = tp(float(seg[1]), float(seg[2]))
                segs.append(("L", x, y))
            else:
                a = tp(float(seg[1]), float(seg[2]))
                b = tp(float(seg[3]), float(seg[4]))
                c = tp(float(seg[5]), float(seg[6]))
                segs.append(("C", a[0], a[1], b[0], b[1], c[0], c[1]))
        return ContourPath(start=start, segs=segs)

    def reversed(self) -> ContourPath:
        """向き反転（制御点順も入れ替え）。閉路では start は同一点のまま。"""
        pts: list[Point] = [self.start]
        ctrls: list[tuple[Point, Point] | None] = []
        for seg in self.segs:
            if seg[0] == "L":
                pts.append((float(seg[1]), float(seg[2])))
                ctrls.append(None)
            else:
                c1 = (float(seg[1]), float(seg[2]))
                c2 = (float(seg[3]), float(seg[4]))
                end = (float(seg[5]), float(seg[6]))
                pts.append(end)
                ctrls.append((c1, c2))
        if not ctrls:
            return ContourPath(start=self.start, segs=[])
        new_segs: list[tuple] = []
        for i in range(len(ctrls) - 1, -1, -1):
            dest = pts[i]
            if ctrls[i] is None:
                new_segs.append(("L", dest[0], dest[1]))
            else:
                c1, c2 = ctrls[i]  # type: ignore[misc]
                new_segs.append(
                    ("C", c2[0], c2[1], c1[0], c1[1], dest[0], dest[1])
                )
        return ContourPath(start=pts[-1], segs=new_segs)

    def anchor_count(self) -> int:
        """オンカーブ＋制御点の総数。"""
        n = 1  # start
        for seg in self.segs:
            if seg[0] == "L":
                n += 1
            else:
                n += 3  # c1,c2,end
        return n

    def sample(self, n_per_seg: int = 24) -> list[Point]:
        out: list[Point] = [self.start]
        cur = self.start
        for seg in self.segs:
            if seg[0] == "L":
                end = (float(seg[1]), float(seg[2]))
                for i in range(1, n_per_seg + 1):
                    t = i / n_per_seg
                    out.append(
                        (cur[0] + (end[0] - cur[0]) * t, cur[1] + (end[1] - cur[1]) * t)
                    )
                cur = end
            else:
                p0 = cur
                p1 = (float(seg[1]), float(seg[2]))
                p2 = (float(seg[3]), float(seg[4]))
                p3 = (float(seg[5]), float(seg[6]))
                for i in range(1, n_per_seg + 1):
                    t = i / n_per_seg
                    out.append(_cubic_point(p0, p1, p2, p3, t))
                cur = p3
        return out


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        (u * u * u) * p0[0]
        + 3 * u * u * t * p1[0]
        + 3 * u * t * t * p2[0]
        + t * t * t * p3[0],
        (u * u * u) * p0[1]
        + 3 * u * u * t * p1[1]
        + 3 * u * t * t * p2[1]
        + t * t * t * p3[1],
    )


def _cubic_deriv(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        3 * u * u * (p1[0] - p0[0])
        + 6 * u * t * (p2[0] - p1[0])
        + 3 * t * t * (p3[0] - p2[0]),
        3 * u * u * (p1[1] - p0[1])
        + 6 * u * t * (p2[1] - p1[1])
        + 3 * t * t * (p3[1] - p2[1]),
    )


def _open_ring(points: Sequence[Point]) -> list[Point]:
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def _arc_lengths(pts: Sequence[Point], closed: bool = False) -> list[float]:
    n = len(pts)
    s = [0.0]
    for i in range(1, n):
        s.append(s[-1] + _dist(pts[i], pts[i - 1]))
    if closed and n >= 2:
        s.append(s[-1] + _dist(pts[0], pts[-1]))
    return s


def detect_corners(
    points: Sequence[Point],
    *,
    angle_deg: float = 30.0,
    min_sep_upm: float = 10.0,
) -> list[int]:
    """閉輪郭の角インデックス（転向角 > angle_deg、弧長で間引き）。"""
    pts = _open_ring(points)
    n = len(pts)
    if n < 3:
        return list(range(n))
    thr = math.radians(angle_deg)
    raw: list[tuple[int, float]] = []  # (index, turn)
    for i in range(n):
        a = pts[(i - 1) % n]
        b = pts[i]
        c = pts[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*v1)
        l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            raw.append((i, math.pi))
            continue
        dot = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        turn = abs(math.acos(dot))
        if turn > thr:
            raw.append((i, turn))

    if not raw:
        return []

    # 転向が大きい順に採用し、弧長 min_sep 未満は捨てる
    raw.sort(key=lambda x: -x[1])
    alen = _arc_lengths(pts, closed=True)
    total = alen[-1] if alen else 0.0
    kept: list[int] = []
    kept_s: list[float] = []
    for i, _turn in raw:
        si = alen[i]
        ok = True
        for ks in kept_s:
            d = abs(si - ks)
            d = min(d, total - d) if total > 0 else d
            if d < min_sep_upm:
                ok = False
                break
        if ok:
            kept.append(i)
            kept_s.append(si)
    return sorted(kept)


def _chord_params(pts: Sequence[Point]) -> list[float]:
    u = [0.0]
    for i in range(1, len(pts)):
        u.append(u[-1] + _dist(pts[i], pts[i - 1]))
    total = u[-1]
    if total < 1e-12:
        return [0.0] * len(pts)
    return [x / total for x in u]


def _fit_cubic_with_u(
    pts: Sequence[Point], u: Sequence[float]
) -> tuple[Point, Point, Point, Point] | None:
    if len(pts) < 2:
        return None
    p0 = pts[0]
    p3 = pts[-1]
    if len(pts) == 2:
        p1 = (p0[0] + (p3[0] - p0[0]) / 3.0, p0[1] + (p3[1] - p0[1]) / 3.0)
        p2 = (p0[0] + 2.0 * (p3[0] - p0[0]) / 3.0, p0[1] + 2.0 * (p3[1] - p0[1]) / 3.0)
        return p0, p1, p2, p3

    c00 = c01 = c11 = 0.0
    x0 = y0 = x1 = y1 = 0.0
    for i, (x, y) in enumerate(pts):
        t = u[i]
        b0 = (1 - t) ** 3
        b1 = 3 * (1 - t) ** 2 * t
        b2 = 3 * (1 - t) * t**2
        b3 = t**3
        rx = x - b0 * p0[0] - b3 * p3[0]
        ry = y - b0 * p0[1] - b3 * p3[1]
        c00 += b1 * b1
        c01 += b1 * b2
        c11 += b2 * b2
        x0 += b1 * rx
        y0 += b1 * ry
        x1 += b2 * rx
        y1 += b2 * ry

    det = c00 * c11 - c01 * c01
    if abs(det) < 1e-12:
        p1 = (p0[0] + (p3[0] - p0[0]) / 3.0, p0[1] + (p3[1] - p0[1]) / 3.0)
        p2 = (p0[0] + 2.0 * (p3[0] - p0[0]) / 3.0, p0[1] + 2.0 * (p3[1] - p0[1]) / 3.0)
        return p0, p1, p2, p3

    a1x = (c11 * x0 - c01 * x1) / det
    a2x = (c00 * x1 - c01 * x0) / det
    a1y = (c11 * y0 - c01 * y1) / det
    a2y = (c00 * y1 - c01 * y0) / det
    return p0, (a1x, a1y), (a2x, a2y), p3


def _reparam_newton(
    pts: Sequence[Point],
    cubic: tuple[Point, Point, Point, Point],
    u: list[float],
) -> list[float]:
    """1 ステップ Newton でパラメータ再推定（端点固定）。"""
    p0, p1, p2, p3 = cubic
    out = list(u)
    for i in range(1, len(pts) - 1):
        t = out[i]
        q = _cubic_point(p0, p1, p2, p3, t)
        d = _cubic_deriv(p0, p1, p2, p3, t)
        rx = pts[i][0] - q[0]
        ry = pts[i][1] - q[1]
        num = rx * d[0] + ry * d[1]
        den = d[0] * d[0] + d[1] * d[1]
        if den < 1e-12:
            continue
        t2 = t + num / den
        out[i] = max(0.0, min(1.0, t2))
    # 単調性を強制
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    out[0] = 0.0
    out[-1] = 1.0
    return out


def _fit_cubic(pts: Sequence[Point], *, reparam_iters: int = 3) -> tuple[Point, Point, Point, Point] | None:
    """端点固定の最小二乗 cubic（弦長初期値＋Newton 再パラメータ）。"""
    if len(pts) < 2:
        return None
    u = _chord_params(pts)
    cubic = _fit_cubic_with_u(pts, u)
    if cubic is None:
        return None
    for _ in range(reparam_iters):
        u = _reparam_newton(pts, cubic, u)
        cubic = _fit_cubic_with_u(pts, u)
        if cubic is None:
            return None
    return cubic


def _max_error_cubic(
    pts: Sequence[Point], cubic: tuple[Point, Point, Point, Point]
) -> tuple[float, int]:
    p0, p1, p2, p3 = cubic
    u = _chord_params(pts)
    # 再パラメータ後の誤差評価にも Newton 1 回
    u = _reparam_newton(pts, cubic, u)
    worst = 0.0
    worst_i = 0
    for i, p in enumerate(pts):
        q = _cubic_point(p0, p1, p2, p3, u[i])
        d = _dist(p, q)
        if d > worst:
            worst = d
            worst_i = i
    return worst, worst_i


def _fit_open(
    pts: list[Point],
    *,
    max_error: float,
    depth: int = 0,
    max_depth: int = 14,
) -> list[tuple]:
    """開折れ線 → cubic/line セグメント列（開始点は呼び出し側）。"""
    if len(pts) < 2:
        return []
    if len(pts) == 2:
        return [("L", pts[1][0], pts[1][1])]

    # ほぼ共線なら直線
    if len(pts) >= 3:
        a, b = pts[0], pts[-1]
        mid_err = max(
            _perp_dist_local(p, a, b) for p in pts[1:-1]
        )
        if mid_err <= max_error * 0.5:
            return [("L", b[0], b[1])]

    cubic = _fit_cubic(pts)
    if cubic is None:
        return [("L", pts[1][0], pts[1][1])] + _fit_open(
            pts[1:], max_error=max_error, depth=depth + 1, max_depth=max_depth
        )

    err, idx = _max_error_cubic(pts, cubic)
    if err <= max_error or depth >= max_depth or idx <= 0 or idx >= len(pts) - 1:
        p0, p1, p2, p3 = cubic
        if (
            _dist(p0, p1) < 0.25
            and _dist(p2, p3) < 0.25
            and _dist(p0, p3) > 1e-6
        ):
            return [("L", p3[0], p3[1])]
        return [("C", p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])]

    left = _fit_open(
        pts[: idx + 1], max_error=max_error, depth=depth + 1, max_depth=max_depth
    )
    right = _fit_open(
        pts[idx:], max_error=max_error, depth=depth + 1, max_depth=max_depth
    )
    return left + right


def _perp_dist_local(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    len2 = dx * dx + dy * dy
    if len2 <= 1e-20:
        return _dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / len2
    t = max(0.0, min(1.0, t))
    return _dist(p, (ax + t * dx, ay + t * dy))


def _path_error(path: ContourPath, pts: Sequence[Point]) -> tuple[float, float, float]:
    from engine.curve_refit import max_deviation

    sampled = path.sample(n_per_seg=24)
    err_fwd = max_deviation(pts, sampled)
    err_bwd = max_deviation(sampled, pts)
    return max(err_fwd, err_bwd), err_fwd, err_bwd


def _seg_end(seg: tuple) -> Point:
    if seg[0] == "L":
        return (float(seg[1]), float(seg[2]))
    return (float(seg[5]), float(seg[6]))


def _try_merge_segs(
    start: Point,
    segs: list[tuple],
    pts: Sequence[Point],
    *,
    max_error_upm: float,
) -> list[tuple]:
    """隣接セグメントを全体誤差ゲート付きで統合。"""
    if len(segs) < 2:
        return segs

    from engine.curve_refit import max_deviation

    def origin_at(segs_in: list[tuple], idx: int) -> Point:
        cur = start
        for s in segs_in[:idx]:
            cur = _seg_end(s)
        return cur

    def err_of(segs_in: list[tuple]) -> float:
        sampled = ContourPath(start=start, segs=segs_in).sample(n_per_seg=12)
        return max(max_deviation(pts, sampled), max_deviation(sampled, pts))

    i = 0
    guard = 0
    max_guards = max(24, len(segs) * 3)
    while i < len(segs) - 1 and guard < max_guards:
        guard += 1
        cur = origin_at(segs, i)
        end2 = _seg_end(segs[i + 1])
        mid_path = ContourPath(start=cur, segs=[segs[i], segs[i + 1]])
        chain = mid_path.sample(n_per_seg=8)
        chain_u = [chain[0]]
        for q in chain[1:]:
            if _dist(q, chain_u[-1]) > 1e-9:
                chain_u.append(q)
        if len(chain_u) < 2:
            i += 1
            continue
        cubic = _fit_cubic(chain_u, reparam_iters=1)
        if cubic is None:
            i += 1
            continue
        _p0, p1, p2, _p3 = cubic
        merged_seg: tuple = ("C", p1[0], p1[1], p2[0], p2[1], end2[0], end2[1])
        # 局所誤差で足切りしてから全体評価
        if _max_error_cubic(chain_u, (_p0, p1, p2, end2))[0] > max_error_upm + 1e-6:
            i += 1
            continue
        trial = segs[:i] + [merged_seg] + segs[i + 2 :]
        if err_of(trial) <= max_error_upm + 1e-6:
            segs = trial
            continue
        i += 1
    return segs


def _fit_once(
    pts: list[Point],
    *,
    max_error_upm: float,
    corner_deg: float,
    min_sep_upm: float,
    fit_error: float,
) -> tuple[ContourPath, dict[str, Any]]:
    corners = detect_corners(pts, angle_deg=corner_deg, min_sep_upm=min_sep_upm)
    if not corners:
        i_far = max(range(1, len(pts)), key=lambda i: _dist(pts[i], pts[0]))
        corners = sorted({0, i_far})
    corners = sorted(set(corners))

    segs: list[tuple] = []
    start = pts[corners[0]]
    for ci in range(len(corners)):
        a = corners[ci]
        b = corners[(ci + 1) % len(corners)]
        if b > a:
            chain = pts[a : b + 1]
        else:
            chain = pts[a:] + pts[: b + 1]
        if len(chain) < 2:
            continue
        segs.extend(_fit_open(chain, max_error=fit_error))

    segs = _try_merge_segs(start, segs, pts, max_error_upm=max_error_upm)
    path = ContourPath(start=start, segs=segs)
    err, err_fwd, err_bwd = _path_error(path, pts)
    meta = {
        "corners": corners,
        "n_corners": len(corners),
        "n_segs": len(segs),
        "n_cubic": sum(1 for s in segs if s[0] == "C"),
        "n_line": sum(1 for s in segs if s[0] == "L"),
        "anchor_count": path.anchor_count(),
        "max_error": err,
        "max_error_fwd": err_fwd,
        "max_error_bwd": err_bwd,
        "max_error_upm": max_error_upm,
        "corner_deg": corner_deg,
        "fit_error": fit_error,
        "min_sep_upm": min_sep_upm,
        "points_source": len(pts),
    }
    return path, meta


def fit_closed_contour(
    points: Sequence[Point],
    *,
    max_error_upm: float = 0.5,
    corner_deg: float = 30.0,
    max_anchors: int | None = None,
    min_sep_upm: float = 10.0,
) -> tuple[ContourPath, dict[str, Any]]:
    """閉折れ線を ContourPath にフィット。

    ゲート未達なら角閾値・分割誤差を段階的に調整して再試行する。
    """
    pts = _open_ring(points)
    if len(pts) < 3:
        raise ValueError("need ≥3 points for closed cubic fit")

    # (corner_deg, fit_error, min_sep) — 少数試行（merge が高コスト）
    trials: list[tuple[float, float, float]] = [
        (corner_deg, max_error_upm * 0.85, min_sep_upm),
        (corner_deg + 10.0, max_error_upm * 0.75, min_sep_upm * 1.2),
        (max(25.0, corner_deg - 5.0), max_error_upm * 0.6, min_sep_upm * 0.8),
    ]

    best: tuple[ContourPath, dict[str, Any]] | None = None
    # (over_err, over_anc, err, anc) — ゲート超過を最優先で最小化
    best_score: tuple[float, float, float, float] | None = None

    for cdeg, ferr, msep in trials:
        path, meta = _fit_once(
            pts,
            max_error_upm=max_error_upm,
            corner_deg=cdeg,
            min_sep_upm=msep,
            fit_error=max(0.15, ferr),
        )
        err = float(meta["max_error"])
        anc = int(meta["anchor_count"])
        over_err = max(0.0, err - max_error_upm)
        over_anc = (
            max(0.0, float(anc - max_anchors)) if max_anchors is not None else 0.0
        )
        score = (over_err, over_anc, err, float(anc))
        if best_score is None or score < best_score:
            best = (path, meta)
            best_score = score
            if over_err <= 1e-9 and over_anc <= 1e-9:
                break

    assert best is not None
    path, meta = best
    meta["trials"] = len(trials)
    return path, meta


def hausdorff_path_to_polyline(path: ContourPath, original: Sequence[Point]) -> float:
    """フィットパス（密サンプル）と原折れ線の max_deviation（双方向）。"""
    from engine.curve_refit import max_deviation

    sampled = path.sample(n_per_seg=24)
    return max(max_deviation(original, sampled), max_deviation(sampled, original))
