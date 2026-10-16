"""当て直した輪郭の凸凹を取る後処理。くちばしの端を持つ字（S）だけにかける。

当て直しは、ゆるい曲線の一部を直線にし、滑らかなはずの節点で接線を 2–4° 折り、
両側の曲がりの強さも揃えない。曲線の途中に平らな所と膝ができる。ここでは:

1. 両端が滑らかに繋がる直線を cubic に戻す
2. 極値でも角でもない節点を抜き、両隣を 1 本にまとめる（折れ線から tol_merge 以内のときだけ）
3. 滑らかな節点で、接線を一直線にし、両側の曲がりを揃える。極値は取っ手を軸に揃える。
   極値でない節点は輪郭に沿って滑らせてよい。折れ線からの距離は両向きで hard 以内に保つ

節点の数と極値は増やさない。numpy は書き出しの依存（bridge）にある。
"""

from __future__ import annotations

import math

from engine.curve_fit import ContourPath

_SMOOTH_DEG = 6.0
_AXIS_DEG = 2.5
_WINDOW = 40
# 当て直しの誤差がこれを超える区間は、超えた分を強く引き戻す。
_CAP = 1.2
# 20 UPM 進む間の曲がりの変わりがこれを超える分を罰する。
_KNEE = 0.004
_KNEE_W = 1e8
# 制御多角形の長さがこれを超える cubic は、形を変えずに二つに割ってから揃える。
_SPLIT = 300.0


def _np():
    import numpy as np

    return np


def _cr(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _bases(n: int):
    np = _np()
    t = np.linspace(0.0, 1.0, n)
    u = 1.0 - t
    return np.stack([u**3, 3 * u * u * t, 3 * u * t * t, t**3], axis=1)


def _curv(p0, p1, p2, p3, t):
    np = _np()
    u = 1 - t
    d1 = (
        (3 * u * u)[:, None] * (p1 - p0)
        + (6 * u * t)[:, None] * (p2 - p1)
        + (3 * t * t)[:, None] * (p3 - p2)
    )
    d2 = (6 * u)[:, None] * (p2 - 2 * p1 + p0) + (6 * t)[:, None] * (p3 - 2 * p2 + p1)
    n = np.maximum(np.hypot(d1[:, 0], d1[:, 1]), 1e-9)
    return _cr(d1, d2) / n**3


def _inner_extremum(p0, p1, p2, p3, margin: float) -> bool:
    """端から margin より離れた所に極値があれば True。"""
    for ax in (0, 1):
        a = -p0[ax] + 3 * p1[ax] - 3 * p2[ax] + p3[ax]
        b = 2 * (p0[ax] - 2 * p1[ax] + p2[ax])
        c = p1[ax] - p0[ax]
        roots = []
        if abs(a) < 1e-12:
            if abs(b) > 1e-12:
                roots.append(-c / b)
        else:
            disc = b * b - 4 * a * c
            if disc >= 0:
                r = math.sqrt(disc)
                roots += [(-b + r) / (2 * a), (-b - r) / (2 * a)]
        for t in roots:
            if 0.0 < t < 1.0:
                u = 1 - t
                v = (
                    u**3 * p0[ax]
                    + 3 * u * u * t * p1[ax]
                    + 3 * u * t * t * p2[ax]
                    + t**3 * p3[ax]
                )
                if min(abs(v - p0[ax]), abs(v - p3[ax])) > margin:
                    return True
    return False


def _is_extremum(prev, p, nxt) -> bool:
    for ax in (0, 1):
        if (prev[ax] - p[ax]) * (nxt[ax] - p[ax]) > 0:
            return True
        if abs(prev[ax] - p[ax]) < 0.5 and abs(nxt[ax] - p[ax]) < 0.5:
            return True
    return False


def _snap_dir(origin, length, ux, uy):
    """origin から (ux, uy) の向きに length 先の、整数の格子点で向きのずれが最も小さい点。"""
    tx, ty = origin[0] + ux * length, origin[1] + uy * length
    best = None
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            px, py = round(tx) + dx, round(ty) + dy
            vx, vy = px - origin[0], py - origin[1]
            n = math.hypot(vx, vy)
            if n < 1:
                continue
            err = abs(vx * uy - vy * ux) / n + 0.01 * abs(n - length)
            if best is None or err < best[0]:
                best = (err, px, py)
    return best[1], best[2]


def _arc(indices, n: int, margin: int):
    """輪郭の番号の集まりを覆う、一続きの区間（前後に margin）。"""
    np = _np()
    if len(indices) == 0:
        return np.arange(n)
    idx = np.sort(np.unique(indices))
    gaps = np.diff(np.concatenate([idx, [idx[0] + n]]))
    k = int(np.argmax(gaps))
    start = int(idx[(k + 1) % len(idx)])
    span = int((idx[k] - start) % n)
    if span + 2 * margin >= n:
        return np.arange(n)
    return (np.arange(start - margin, start + span + margin + 1)) % n


class _Polygon:
    def __init__(self, points):
        np = _np()
        self.a = np.asarray(points, float)
        self.b = np.roll(self.a, -1, axis=0)
        self.n = len(self.a)
        seg = np.hypot(*(self.b - self.a).T)
        self.cum = np.concatenate([[0.0], np.cumsum(seg)])

    def dist(self, pts, idx):
        """pts から、番号 idx の辺への距離の最小。"""
        np = _np()
        a = self.a[idx]
        ab = self.b[idx] - a
        l2 = np.maximum((ab**2).sum(1), 1e-12)
        t = np.clip(((pts[:, None, :] - a[None]) * ab[None]).sum(-1) / l2[None], 0, 1)
        q = a[None] + t[..., None] * ab[None]
        return np.sqrt(((pts[:, None, :] - q) ** 2).sum(-1)).min(1)

    def near(self, pts, limit):
        np = _np()
        d = np.sqrt(((self.a[:, None, :] - pts[None]) ** 2).sum(-1)).min(1)
        return np.nonzero(d < limit)[0]

    def at(self, s):
        np = _np()
        s %= self.cum[-1]
        k = int(np.searchsorted(self.cum, s, side="right") - 1)
        k = min(k, self.n - 1)
        t = (s - self.cum[k]) / max(self.cum[k + 1] - self.cum[k], 1e-12)
        return self.a[k] + (self.b[k] - self.a[k]) * t


def _starts(path: ContourPath):
    out = []
    cur = path.start
    for s in path.segs:
        out.append(cur)
        cur = (s[1], s[2]) if s[0] == "L" else (s[5], s[6])
    return out


def _split_long(path: ContourPath) -> ContourPath:
    segs: list[tuple] = []
    for p0, seg in zip(_starts(path), path.segs, strict=True):
        if seg[0] != "C":
            segs.append(seg)
            continue
        p1, p2, p3 = seg[1:3], seg[3:5], seg[5:7]
        if math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3) <= _SPLIT:
            segs.append(seg)
            continue

        def mid(a, b):
            return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)

        a, b, c = mid(p0, p1), mid(p1, p2), mid(p2, p3)
        d, e = mid(a, b), mid(b, c)
        f = mid(d, e)
        segs.append(("C", *a, *d, *f))
        segs.append(("C", *e, *c, *p3))
    return ContourPath(start=path.start, segs=segs)


def _turn(a, b) -> float:
    return abs(
        math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
    )


def _curve_lines(path: ContourPath) -> ContourPath:
    """両端が滑らかに繋がる直線を、取っ手を弦の 1/3 に置いた cubic にする。"""
    segs = list(path.segs)
    m = len(segs)
    starts = _starts(path)

    def head(k):
        s = segs[k]
        return (s[1] - starts[k][0], s[2] - starts[k][1])

    def tail(k):
        s = segs[k]
        if s[0] == "L":
            return (s[1] - starts[k][0], s[2] - starts[k][1])
        return (s[5] - s[3], s[6] - s[4])

    out = list(segs)
    for k, s in enumerate(segs):
        if s[0] != "L":
            continue
        d = (s[1] - starts[k][0], s[2] - starts[k][1])
        if (
            _turn(tail((k - 1) % m), d) < _SMOOTH_DEG
            and _turn(d, head((k + 1) % m)) < _SMOOTH_DEG
        ):
            x0, y0 = starts[k]
            out[k] = (
                "C",
                x0 + d[0] / 3,
                y0 + d[1] / 3,
                x0 + 2 * d[0] / 3,
                y0 + 2 * d[1] / 3,
                s[1],
                s[2],
            )
    return ContourPath(start=path.start, segs=out)


def _merge_nodes(path: ContourPath, poly: _Polygon, tol: float) -> ContourPath:
    """極値でも角でもない節点を抜き、両隣の cubic を 1 本にできれば置き換える。"""
    np = _np()
    base = _bases(21)
    dense = _bases(81)
    grid = np.linspace(0.1, 0.7, 25)
    start = path.start
    segs = list(path.segs)
    while True:
        starts = _starts(ContourPath(start=start, segs=segs))
        best = None
        for i in range(len(segs) - 1):
            j = i + 1
            first, second = segs[i], segs[j]
            if first[0] != "C" or second[0] != "C":
                continue
            p0 = np.array(starts[i], float)
            p = np.array(first[5:7], float)
            p3 = np.array(second[5:7], float)
            h_in = np.array(first[3:5], float)
            h_out = np.array(second[1:3], float)
            vin, vout = p - h_in, h_out - p
            if (
                np.hypot(*vin) < 1e-6
                or np.hypot(*vout) < 1e-6
                or _turn(vin, vout) > _SMOOTH_DEG
            ):
                continue
            if _is_extremum(h_in, p, h_out):
                continue
            u0 = np.array(first[1:3], float) - p0
            u3 = p3 - np.array(second[3:5], float)
            if np.hypot(*u0) < 1e-6 or np.hypot(*u3) < 1e-6:
                continue
            u0 /= np.hypot(*u0)
            u3 /= np.hypot(*u3)
            old = np.concatenate(
                [
                    dense @ np.array([p0, np.array(first[1:3], float), h_in, p]),
                    dense @ np.array([p, h_out, np.array(second[3:5], float), p3]),
                ]
            )
            owned = poly.near(old, 1.5)
            own = poly.a[owned]
            window = _arc(owned, poly.n, 10)
            chord = float(np.hypot(*(p3 - p0)))
            for la in grid * chord:
                for lb in grid * chord:
                    c1 = p0 + u0 * la
                    c2 = p3 - u3 * lb
                    if _inner_extremum(p0, c1, c2, p3, 0.8):
                        continue
                    err = float(
                        poly.dist(base @ np.array([p0, c1, c2, p3]), window).max()
                    )
                    if err > tol or (best is not None and err >= best[0]):
                        continue
                    if len(own):
                        q = dense @ np.array([p0, c1, c2, p3])
                        back = float(
                            np.sqrt(((own[:, None, :] - q[None]) ** 2).sum(-1))
                            .min(1)
                            .max()
                        )
                        err = max(err, back)
                    if err <= tol and (best is None or err < best[0]):
                        best = (err, i, j, c1, c2, p3)
        if best is None:
            break
        _err, i, j, c1, c2, p3 = best
        segs[i] = (
            "C",
            round(c1[0]),
            round(c1[1]),
            round(c2[0]),
            round(c2[1]),
            int(p3[0]),
            int(p3[1]),
        )
        del segs[j]
    return ContourPath(start=start, segs=segs)


class _Fair:
    def __init__(self, path: ContourPath, poly: _Polygon, *, tol: float, wj: float):
        np = _np()
        self.poly = poly
        self.tol = tol
        self.wj = wj
        self.base = _bases(21)
        self.dense = _bases(81)
        self.tk = np.linspace(0.0, 1.0, 9)
        self.tkb = _bases(9)
        self.start = path.start
        self.kind = []
        self.pts = []
        cur = np.array(path.start, float)
        for seg in path.segs:
            if seg[0] == "L":
                end = np.array(seg[1:3], float)
                self.kind.append("L")
                self.pts.append([cur, cur, end, end])
            else:
                self.kind.append("C")
                self.pts.append(
                    [
                        cur,
                        np.array(seg[1:3], float),
                        np.array(seg[3:5], float),
                        np.array(seg[5:7], float),
                    ]
                )
            cur = self.pts[-1][3]
        m = len(self.kind)
        self.joins = []
        for i in range(m):
            j = (i + 1) % m
            if self.kind[i] != "C" or self.kind[j] != "C":
                continue
            p = self.pts[i][3]
            vin = p - self.pts[i][2]
            vout = self.pts[j][1] - p
            lin, lout = float(np.hypot(*vin)), float(np.hypot(*vout))
            if lin < 1e-6 or lout < 1e-6 or _turn(vin, vout) > _SMOOTH_DEG:
                continue
            d = vin / lin + vout / lout
            theta = math.atan2(d[1], d[0])
            deg = math.degrees(theta) % 90.0
            axis = min(deg, 90.0 - deg) < _AXIS_DEG
            if axis:
                theta = round(theta / (math.pi / 2)) * (math.pi / 2)
            join = {
                "i": i,
                "j": j,
                "theta": theta,
                "axis": axis,
                "lin": lin,
                "lout": lout,
                "s": None,
            }
            if not axis:
                k = int(np.argmin(np.hypot(*(poly.a - p).T)))
                join["s"] = join["s0"] = float(poly.cum[k])
                join["off"] = p - poly.at(join["s"])
            self.joins.append(join)
        self._apply()
        self.hard = {}
        self.had_ext = set()
        owner = np.full(poly.n, -1)
        best = np.full(poly.n, np.inf)
        for i, seg in enumerate(self.pts):
            d = np.sqrt(
                ((poly.a[:, None, :] - (self.dense @ np.array(seg))[None]) ** 2).sum(-1)
            ).min(1)
            take = d < best
            best[take] = d[take]
            owner[take] = i
        self.owned = {i: poly.a[owner == i] for i in range(m)}
        self.back = {
            i: float(best[owner == i].max()) if (owner == i).any() else 0.0
            for i in range(m)
        }
        self.window = {}
        for i in range(m):
            idx = np.nonzero(owner == i)[0]
            self.window[i] = _arc(idx, poly.n, _WINDOW)
        for i, kind in enumerate(self.kind):
            if kind != "C":
                continue
            self.hard[i] = max(
                _CAP,
                float(
                    self.poly.dist(
                        self.base @ np.array(self.pts[i]), self.window[i]
                    ).max()
                )
                + 0.05,
            )
            if _inner_extremum(*self.pts[i], 0.8):
                self.had_ext.add(i)
        self.neigh = {}
        for jn in self.joins:
            pair = {jn["i"], jn["j"]}
            ids = set(pair)
            for other in self.joins:
                if other["i"] in pair or other["j"] in pair:
                    ids |= {other["i"], other["j"]}
            self.neigh[id(jn)] = ids

    def _apply(self):
        np = _np()
        for jn in self.joins:
            if jn["s"] is not None:
                p = self.poly.at(jn["s"]) + jn["off"]
                self.pts[jn["i"]][3] = p
                self.pts[jn["j"]][0] = p
            p = self.pts[jn["i"]][3]
            u = np.array([math.cos(jn["theta"]), math.sin(jn["theta"])])
            self.pts[jn["i"]][2] = p - u * jn["lin"]
            self.pts[jn["j"]][1] = p + u * jn["lout"]

    def cost(self, segs):
        np = _np()
        self._apply()
        m = len(self.pts)
        c = 0.0
        for i in segs:
            if self.kind[i] != "C":
                continue
            d = self.poly.dist(self.base @ np.array(self.pts[i]), self.window[i])
            worst = float(d.max())
            if worst > self.hard[i]:
                return math.inf
            c += 1e6 * max(0.0, worst - _CAP) ** 2
            if i not in self.had_ext and _inner_extremum(*self.pts[i], 0.8):
                return math.inf
            own = self.owned[i]
            if len(own):
                q = np.concatenate(
                    [self.dense @ np.array(self.pts[(i + o) % m]) for o in (-1, 0, 1)]
                )
                back = float(
                    np.sqrt(((own[:, None, :] - q[None]) ** 2).sum(-1)).min(1).max()
                )
                if back > max(_CAP, self.back[i] + 0.05):
                    return math.inf
                c += 1e6 * max(0.0, back - _CAP) ** 2
            c += 200.0 * float((np.clip(d - self.tol, 0, None) ** 2).sum())
            k = _curv(*self.pts[i], self.tk)
            c += 2e5 * float((np.diff(k, 2) ** 2).sum())
            ds = np.maximum(
                np.hypot(*np.diff(self.tkb @ np.array(self.pts[i]), axis=0).T), 1e-6
            )
            slope = np.abs(np.diff(k)) / ds * 20.0
            c += _KNEE_W * float((np.clip(slope - _KNEE, 0, None) ** 2).sum())
        for jn in self.joins:
            if jn["i"] not in segs and jn["j"] not in segs:
                continue
            k1 = _curv(*self.pts[jn["i"]], np.array([1.0]))[0]
            k0 = _curv(*self.pts[jn["j"]], np.array([0.0]))[0]
            c += (self.wj * (k1 - k0)) ** 2
        return c

    def run(self, iters: int):
        steps = (
            ("theta", (-0.02, -0.004, -0.001, 0.001, 0.004, 0.02)),
            ("lin", (0.8, 0.9, 0.97, 1.03, 1.1, 1.25)),
            ("lout", (0.8, 0.9, 0.97, 1.03, 1.1, 1.25)),
            ("s", (-8.0, -2.0, -0.5, 0.5, 2.0, 8.0)),
        )
        for _ in range(iters):
            moved = False
            for jn in self.joins:
                segs = self.neigh[id(jn)]
                for key, options in steps:
                    if key == "theta" and jn["axis"]:
                        continue
                    if key == "s" and jn["s"] is None:
                        continue
                    here = jn[key]
                    best = self.cost(segs)
                    choice = here
                    for step in options:
                        trial = here + step if key in ("theta", "s") else here * step
                        if key == "s" and abs(trial - jn["s0"]) > 30.0:
                            continue
                        jn[key] = trial
                        c = self.cost(segs)
                        if c < best - 1e-9:
                            best, choice = c, trial
                    jn[key] = choice
                    moved |= choice != here
            if not moved:
                break
        self._apply()
        return self

    def path(self) -> ContourPath:
        np = _np()
        for jn in self.joins:
            p = np.round(self.pts[jn["i"]][3])
            self.pts[jn["i"]][3] = p
            self.pts[jn["j"]][0] = p
            u = (math.cos(jn["theta"]), math.sin(jn["theta"]))
            if jn["axis"]:
                self.pts[jn["i"]][2] = np.round(p - np.array(u) * jn["lin"])
                self.pts[jn["j"]][1] = np.round(p + np.array(u) * jn["lout"])
            else:
                self.pts[jn["i"]][2] = np.array(
                    _snap_dir(p, jn["lin"], -u[0], -u[1]), float
                )
                self.pts[jn["j"]][1] = np.array(
                    _snap_dir(p, jn["lout"], u[0], u[1]), float
                )
        segs = []
        for kind, (_p0, p1, p2, p3) in zip(self.kind, self.pts, strict=True):
            if kind == "L":
                segs.append(("L", round(float(p3[0])), round(float(p3[1]))))
            else:
                segs.append(
                    (
                        "C",
                        round(float(p1[0])),
                        round(float(p1[1])),
                        round(float(p2[0])),
                        round(float(p2[1])),
                        round(float(p3[0])),
                        round(float(p3[1])),
                    )
                )
        start = self.pts[0][0]
        return ContourPath(
            start=(round(float(start[0])), round(float(start[1]))), segs=segs
        )


def fair_contour(
    path: ContourPath,
    points: list[tuple[float, float]],
    *,
    tol: float = 1.0,
    tol_merge: float = 0.6,
    wj: float = 1e4,
    iters: int = 150,
) -> ContourPath:
    ring = points[:-1] if len(points) > 1 and points[0] == points[-1] else list(points)
    poly = _Polygon(ring)
    merged = _split_long(_merge_nodes(_curve_lines(path), poly, tol_merge))
    return _Fair(merged, poly, tol=tol, wj=wj).run(iters).path()
