"""節点列を Hobby（1985）の cubic 列へ展開する。

速度 ρ, σ は論文の式 (10) の METAFONT 定数（√2、1/16、(3−√5)/2）。
接線角は、曲率の (θ, φ) = (0, 0) での一次項（モック曲率）を節点で連続にする
三重対角方程式で決める。curl は端点で 1。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.latin.schema import Knot, Stroke

_SQRT2 = math.sqrt(2)
_B = 1.0 / 16.0
_C = (3.0 - math.sqrt(5.0)) / 2.0


@dataclass(frozen=True)
class Cubic:
    p0: tuple[float, float]
    c1: tuple[float, float]
    c2: tuple[float, float]
    p1: tuple[float, float]


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _rho_sigma(theta: float, phi: float) -> tuple[float, float]:
    st, ct = math.sin(theta), math.cos(theta)
    sf, cf = math.sin(phi), math.cos(phi)
    alpha = _SQRT2 * (st - _B * sf) * (sf - _B * st) * (ct - cf)
    rho = (2.0 + alpha) / (1.0 + (1.0 - _C) * ct + _C * cf)
    alpha_end = _SQRT2 * (sf - _B * st) * (st - _B * sf) * (cf - ct)
    sigma = (2.0 + alpha_end) / (1.0 + (1.0 - _C) * cf + _C * ct)
    return rho, sigma


def _mock(first: float, second: float, tension: float) -> float:
    """モック曲率の一次項。引数は (出発側の角, 到着側の角)。"""
    return tension**2 * ((2.0 / tension - 6.0) * first + (2.0 / tension) * second)


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(rhs)
    a = [row[:] for row in matrix]
    b = rhs[:]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            continue
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        scale = a[col][col]
        for j in range(col, n):
            a[col][j] /= scale
        b[col] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor == 0.0:
                continue
            for j in range(col, n):
                a[row][j] -= factor * a[col][j]
            b[row] -= factor * b[col]
    return b


def _coeffs(tension: float) -> tuple[float, float]:
    """mock(first, second) = a * first + b * second。"""
    return (2.0 * tension - 6.0 * tension * tension, 2.0 * tension)


def _closed_angles(
    delta: list[float],
    dist: list[float],
    tensions: list[float],
    fixed: dict[int, float],
) -> list[float]:
    """閉じた列。未知数は弦からの出発角 θ。絶対角は δ + θ。"""
    n = len(delta)
    psi = [_wrap(delta[i] - delta[(i - 1) % n]) for i in range(n)]
    theta_fixed = {i: _wrap(omega - delta[i]) for i, omega in fixed.items()}
    unknowns = [i for i in range(n) if i not in theta_fixed]
    if not unknowns:
        return [delta[i] + theta_fixed[i] for i in range(n)]
    index = {knot: col for col, knot in enumerate(unknowns)}
    m = len(unknowns)
    matrix = [[0.0] * m for _ in range(m)]
    rhs = [0.0] * m

    def add_theta(row: int, knot: int, coeff: float) -> None:
        if knot in theta_fixed:
            rhs[row] -= coeff * theta_fixed[knot]
        else:
            matrix[row][index[knot]] += coeff

    for row, i in enumerate(unknowns):
        prev = (i - 1) % n
        nxt = (i + 1) % n
        a_s, b_s = _coeffs(tensions[prev])
        a_t, b_t = _coeffs(tensions[i])
        d_prev = dist[prev]
        d_next = dist[i]
        add_theta(row, prev, b_s / d_prev)
        add_theta(row, i, -a_s / d_prev - a_t / d_next)
        add_theta(row, nxt, b_t / d_next)
        rhs[row] += (a_s / d_prev) * psi[i]
        rhs[row] -= (b_t / d_next) * psi[nxt]

    solved = _solve(matrix, rhs)
    theta = [theta_fixed.get(i, 0.0) for i in range(n)]
    for knot, col in index.items():
        theta[knot] = solved[col]
    return [delta[i] + theta[i] for i in range(n)]


def _open_angles(
    delta: list[float],
    dist: list[float],
    tensions: list[float],
    fixed: dict[int, float],
) -> list[float]:
    """開いた列。未知数は各区間の出発角 θ と、終端の到着角 φ。"""
    nseg = len(delta)
    n = nseg + 1
    psi = {i: _wrap(delta[i] - delta[i - 1]) for i in range(1, n - 1)}
    theta_fixed: dict[int, float] = {}
    phi_fixed: float | None = None
    for knot, omega in fixed.items():
        if knot == n - 1:
            phi_fixed = _wrap(delta[-1] - omega)
        else:
            theta_fixed[knot] = _wrap(omega - delta[knot])

    names: list[tuple[str, int]] = []
    for i in range(n - 1):
        if i not in theta_fixed:
            names.append(("theta", i))
    if phi_fixed is None:
        names.append(("phi", n - 1))
    if not names:
        theta = [theta_fixed[i] for i in range(n - 1)]
        phi_end = phi_fixed if phi_fixed is not None else 0.0
        return [delta[i] + theta[i] for i in range(n - 1)] + [delta[-1] - phi_end]

    index = {name: col for col, name in enumerate(names)}
    m = len(names)
    matrix = [[0.0] * m for _ in range(m)]
    rhs = [0.0] * m

    def add(row: int, kind: str, knot: int, coeff: float) -> None:
        if kind == "phi" and phi_fixed is not None:
            rhs[row] -= coeff * phi_fixed
            return
        if kind == "theta" and knot in theta_fixed:
            rhs[row] -= coeff * theta_fixed[knot]
            return
        matrix[row][index[(kind, knot)]] += coeff

    row = 0

    def start_curl() -> None:
        # θ0 = φ1 = −ψ1 − θ1
        add(row, "theta", 0, 1.0)
        add(row, "theta", 1, 1.0)
        rhs[row] -= psi[1]

    def end_curl() -> None:
        # φ_end = θ_{n-2}
        add(row, "phi", n - 1, 1.0)
        add(row, "theta", n - 2, -1.0)

    def continuity(i: int) -> None:
        prev = i - 1
        a_s, b_s = _coeffs(tensions[prev])
        a_t, b_t = _coeffs(tensions[i])
        d_prev = dist[prev]
        d_next = dist[i]
        add(row, "theta", prev, b_s / d_prev)
        add(row, "theta", i, -a_s / d_prev - a_t / d_next)
        if i == n - 2:
            add(row, "phi", n - 1, -b_t / d_next)
            rhs[row] += (a_s / d_prev) * psi[i]
        else:
            add(row, "theta", i + 1, b_t / d_next)
            rhs[row] += (a_s / d_prev) * psi[i]
            rhs[row] -= (b_t / d_next) * psi[i + 1]

    if ("theta", 0) in index:
        start_curl()
        row += 1
    for i in range(1, n - 1):
        if ("theta", i) in index:
            continuity(i)
            row += 1
    if ("phi", n - 1) in index:
        end_curl()
        row += 1

    solved = _solve(matrix, rhs)
    theta = [theta_fixed.get(i, 0.0) for i in range(n - 1)]
    phi_end = 0.0 if phi_fixed is None else phi_fixed
    for (kind, knot), col in index.items():
        if kind == "theta":
            theta[knot] = solved[col]
        else:
            phi_end = solved[col]
    return [delta[i] + theta[i] for i in range(n - 1)] + [delta[-1] - phi_end]


def _chain_angles(
    points: list[tuple[float, float]],
    tensions: list[float],
    closed: bool,
    fixed: dict[int, float],
) -> list[float]:
    """各節点の絶対接線角（ラジアン）。fixed は節点番号 → 角度。"""
    n = len(points)
    nseg = n if closed else n - 1
    delta: list[float] = []
    dist: list[float] = []
    for i in range(nseg):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length == 0.0:
            raise ValueError("hobby: zero-length segment")
        delta.append(math.atan2(dy, dx))
        dist.append(length)

    # 2点の開曲線は curl だけでは不定。曲率 0（弦の方向）が θ = φ = 0 の解。
    if not closed and n == 2 and not fixed:
        return [delta[0], delta[0]]

    if closed:
        return _closed_angles(delta, dist, tensions, fixed)
    return _open_angles(delta, dist, tensions, fixed)


def _cubic(p0: tuple[float, float], p1: tuple[float, float], w0: float, w1: float, tension: float) -> Cubic:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    delta = math.atan2(dy, dx)
    theta = _wrap(w0 - delta)
    phi = _wrap(delta - w1)
    rho, sigma = _rho_sigma(theta, phi)
    dist0 = rho * length / (3.0 * tension)
    dist1 = sigma * length / (3.0 * tension)
    c1 = (p0[0] + dist0 * math.cos(w0), p0[1] + dist0 * math.sin(w0))
    c2 = (p1[0] - dist1 * math.cos(w1), p1[1] - dist1 * math.sin(w1))
    return Cubic(p0, c1, c2, p1)


def _line(p0: tuple[float, float], p1: tuple[float, float]) -> Cubic:
    c1 = (p0[0] + (p1[0] - p0[0]) / 3.0, p0[1] + (p1[1] - p0[1]) / 3.0)
    c2 = (p0[0] + 2.0 * (p1[0] - p0[0]) / 3.0, p0[1] + 2.0 * (p1[1] - p0[1]) / 3.0)
    return Cubic(p0, c1, c2, p1)


def _is_line(a: Knot, b: Knot) -> bool:
    return a.kind == "line" or b.kind == "line"


def stroke_tensions(stroke: Stroke) -> tuple[float, ...]:
    count = len(stroke.knots) if stroke.closed else len(stroke.knots) - 1
    if stroke.tensions is not None:
        return stroke.tensions
    value = 1.0 if stroke.tension is None else stroke.tension
    return tuple(value for _ in range(count))


def expand_stroke(stroke: Stroke) -> tuple[Cubic, ...]:
    knots = stroke.knots
    n = len(knots)
    nseg = n if stroke.closed else n - 1
    tensions = stroke_tensions(stroke)
    points = [(k.x, k.y) for k in knots]
    linear = [
        _is_line(knots[i], knots[(i + 1) % n]) if stroke.closed or i + 1 < n else False
        for i in range(nseg)
    ]
    # 直線でも corner でも、接線を共有しない境界でチェーンを切る。
    cubics: list[Cubic | None] = [None] * nseg

    def runs() -> list[tuple[int, int, bool]]:
        """(開始節点, 節点数, 閉じているか)。直線セグメントはチェーンに入れない。"""
        if stroke.closed and not any(linear) and all(k.kind == "smooth" for k in knots):
            return [(0, n, True)]
        found: list[tuple[int, int, bool]] = []
        if stroke.closed:
            # 閉じた列は、直線か corner の直後から次の境界まで。
            breaks = set()
            for i, knot in enumerate(knots):
                if knot.kind == "corner" or linear[i] or linear[(i - 1) % n]:
                    breaks.add(i)
            if not breaks:
                return [(0, n, True)]
            order = sorted(breaks)
            for bi, start in enumerate(order):
                end = order[(bi + 1) % len(order)]
                # start から end まで（end を含む）が1チェーン。間の節点だけ。
                seq = []
                i = start
                while True:
                    seq.append(i)
                    if i == end:
                        break
                    i = (i + 1) % n
                    if len(seq) > n:
                        break
                if len(seq) >= 2:
                    found.append((start, len(seq), False))
            return found
        start = 0
        i = 0
        while i < n - 1:
            boundary = knots[i].kind == "corner" or linear[i]
            if i == 0:
                boundary = False
            if boundary:
                if i - start >= 1:
                    found.append((start, i - start + 1, False))
                start = i
            i += 1
        if n - 1 - start >= 1:
            found.append((start, n - start, False))
        return found

    # 直線は先に埋める。
    for i in range(nseg):
        if linear[i]:
            cubics[i] = _line(points[i], points[(i + 1) % n])

    for start, count, closed in runs():
        if closed:
            idxs = list(range(n))
        else:
            idxs = [(start + k) % n for k in range(count)]
        if len(idxs) < 2:
            continue
        chain_points = [points[k] for k in idxs]
        # チェーン内のセグメント張力。閉じた全体なら全区間。
        if closed:
            chain_t = list(tensions)
        else:
            chain_t = []
            for k in range(len(idxs) - 1):
                seg = idxs[k]
                chain_t.append(tensions[seg])
        fixed: dict[int, float] = {}
        for local, knot_i in enumerate(idxs):
            knot = knots[knot_i]
            if knot.angle_deg is not None and knot.kind == "smooth":
                fixed[local] = math.radians(knot.angle_deg)
            if (
                not closed
                and local in (0, len(idxs) - 1)
                and knot.kind == "corner"
                and knot.angle_deg is not None
            ):
                fixed[local] = math.radians(knot.angle_deg)
        if not closed and all(knots[k].kind == "line" for k in idxs):
            continue
        # 両端が直線セグメントに接する smooth は、直線の方向で接線を固定する。
        angles = _chain_angles(chain_points, chain_t, closed, fixed)
        if closed:
            for i in range(n):
                if cubics[i] is None:
                    cubics[i] = _cubic(points[i], points[(i + 1) % n], angles[i], angles[(i + 1) % n], tensions[i])
        else:
            for local in range(len(idxs) - 1):
                seg = idxs[local]
                if cubics[seg] is None:
                    cubics[seg] = _cubic(
                        points[seg],
                        points[(seg + 1) % n],
                        angles[local],
                        angles[local + 1],
                        tensions[seg],
                    )
    if any(item is None for item in cubics):
        raise ValueError(f"hobby: stroke {stroke.id!r} left a segment unsolved")
    return tuple(item for item in cubics if item is not None)


def expand_same(stroke: Stroke) -> tuple[Cubic, ...]:
    return expand_stroke(stroke)
