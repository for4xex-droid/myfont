"""union 後の曲線再適合（P2++）。

方針（PLAN §4 / snapshots/curve_refit.yaml）:
  - デフォルトは Ramer–Douglas–Peucker による **polyline 簡略化**
  - フル cubic 再適合は M2 では非デフォルト（角・うろこ崩壊リスク）
  - ゲート: contour 数不変 ＋ 原輪郭への max 誤差 ≤ max_error_upm
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Point = tuple[float, float]
RefitMode = Literal["rdp_polyline", "passthrough"]

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "curve_refit.yaml"


@dataclass(frozen=True)
class RefitConfig:
    mode: RefitMode = "rdp_polyline"
    epsilon_upm: float = 1.5
    max_error_upm: float = 1.5
    max_points_soft: int = 120
    min_points: int = 3
    enabled: bool = True


@dataclass
class RefitResult:
    contours: list[list[Point]]
    meta: dict[str, Any] = field(default_factory=dict)


def load_refit_config(path: Path | None = None) -> RefitConfig:
    p = path or _SNAPSHOT
    if not p.is_file():
        raise FileNotFoundError(
            f"curve_refit config missing: {p} (正本 snapshots/curve_refit.yaml)"
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    mode = str(raw.get("mode", "rdp_polyline"))
    if mode not in ("rdp_polyline", "passthrough"):
        raise ValueError(
            f"unsupported curve_refit mode: {mode!r} "
            "(allowed: rdp_polyline, passthrough; cubic is deferred)"
        )
    return RefitConfig(
        mode=mode,  # type: ignore[arg-type]
        epsilon_upm=float(raw.get("epsilon_upm", 1.5)),
        max_error_upm=float(raw.get("max_error_upm", 1.5)),
        max_points_soft=int(raw.get("max_points_soft", 120)),
        min_points=int(raw.get("min_points", 3)),
        enabled=bool(raw.get("enabled", True)),
    )


def _dist(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _perp_dist(p: Point, a: Point, b: Point) -> float:
    """点 p から線分 ab への距離（ゼロ長なら端点距離）。"""
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


def _open_ring(points: Sequence[Point]) -> list[Point]:
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def rdp_open(points: Sequence[Point], epsilon: float) -> list[Point]:
    """開折れ線の Ramer–Douglas–Peucker。"""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 3:
        return pts
    stack = [(0, len(pts) - 1)]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    while stack:
        i0, i1 = stack.pop()
        a, b = pts[i0], pts[i1]
        dmax = -1.0
        idx = -1
        for i in range(i0 + 1, i1):
            d = _perp_dist(pts[i], a, b)
            if d > dmax:
                dmax = d
                idx = i
        if idx >= 0 and dmax > epsilon:
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return [p for p, k in zip(pts, keep) if k]


def rdp_closed(points: Sequence[Point], epsilon: float) -> list[Point]:
    """閉輪郭の RDP（始点と最遠点をアンカーに二分割）。"""
    pts = _open_ring(points)
    if len(pts) <= 3:
        return pts
    i_far = max(range(1, len(pts)), key=lambda i: _dist(pts[i], pts[0]))
    left = rdp_open(pts[: i_far + 1], epsilon)
    right_chain = pts[i_far:] + [pts[0]]
    right = rdp_open(right_chain, epsilon)
    # left の末尾と right の先頭は同じ（i_far）。right 末尾は pts[0]＝left[0]
    merged = left[:-1] + right[:-1]
    if len(merged) < 3:
        return pts
    return merged


def max_deviation(
    original: Sequence[Point], simplified: Sequence[Point]
) -> float:
    """原輪郭各点 → 簡略化輪郭の線分への最大距離（閉路）。"""
    src = _open_ring(original)
    dst = _open_ring(simplified)
    if len(src) < 3 or len(dst) < 3:
        return 0.0
    n = len(dst)
    worst = 0.0
    for p in src:
        best = min(_perp_dist(p, dst[i], dst[(i + 1) % n]) for i in range(n))
        worst = max(worst, best)
    return worst


def refit_contour(
    points: Sequence[Point],
    cfg: RefitConfig,
) -> tuple[list[Point], dict[str, Any]]:
    src = _open_ring(points)
    before_n = len(src)
    if not cfg.enabled or cfg.mode == "passthrough":
        return src, {
            "mode": "passthrough" if cfg.enabled else "disabled",
            "points_before": before_n,
            "points_after": before_n,
            "max_error": 0.0,
            "soft_over_points": before_n > cfg.max_points_soft,
        }

    simplified = rdp_closed(src, cfg.epsilon_upm)
    if len(simplified) < cfg.min_points:
        simplified = src
    err = max_deviation(src, simplified)
    meta = {
        "mode": cfg.mode,
        "points_before": before_n,
        "points_after": len(simplified),
        "max_error": err,
        "epsilon_upm": cfg.epsilon_upm,
        "soft_over_points": len(simplified) > cfg.max_points_soft,
    }
    if err > cfg.max_error_upm + 1e-6:
        raise ValueError(
            f"curve_refit gate failed: max_error={err:.4f} > "
            f"max_error_upm={cfg.max_error_upm}"
        )
    return simplified, meta


def refit_contours(
    contours: Sequence[Sequence[Point]],
    cfg: RefitConfig | None = None,
) -> RefitResult:
    """複数輪郭を再適合。contour 数が変わったら失敗。"""
    cfg = cfg or load_refit_config()
    out: list[list[Point]] = []
    per: list[dict[str, Any]] = []
    for c in contours:
        simp, meta = refit_contour(c, cfg)
        out.append(simp)
        per.append(meta)

    if len(out) != len(contours):
        raise ValueError("curve_refit changed contour count (internal bug)")

    pts_before = sum(m["points_before"] for m in per)
    pts_after = sum(m["points_after"] for m in per)
    worst = max((m["max_error"] for m in per), default=0.0)
    return RefitResult(
        contours=out,
        meta={
            "mode": cfg.mode if cfg.enabled else "disabled",
            "enabled": cfg.enabled,
            "n_contours": len(out),
            "points_before": pts_before,
            "points_after": pts_after,
            "reduction_ratio": (
                (1.0 - pts_after / pts_before) if pts_before else 0.0
            ),
            "max_error": worst,
            "max_error_upm": cfg.max_error_upm,
            "any_soft_over_points": any(m["soft_over_points"] for m in per),
            "per_contour": per,
        },
    )
