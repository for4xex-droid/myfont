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
RefitMode = Literal["rdp_polyline", "passthrough", "cubic_fit"]
KanaMode = Literal["rdp_polyline", "passthrough", "cubic_fit"]

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "curve_refit.yaml"


@dataclass(frozen=True)
class RefitConfig:
    mode: RefitMode = "rdp_polyline"
    epsilon_upm: float = 1.5
    max_error_upm: float = 1.5
    max_points_soft: int = 120
    min_points: int = 3
    enabled: bool = True
    # Phase 1: 仮名専用モード（漢字の mode とは独立）
    kana_mode: KanaMode = "passthrough"
    cubic_max_error_upm: float = 0.5
    cubic_loop_max_error_upm: float = 0.75
    cubic_corner_deg: float = 30.0
    cubic_max_anchors: int = 48
    # overlay 重ね塗りは combined simplify が輪郭数を変えるので見ない
    skip_combined_self_intersect: bool = False


@dataclass
class RefitResult:
    contours: list[list[Point]]
    meta: dict[str, Any] = field(default_factory=dict)
    # Phase 1: cubic_fit 時のみ ContourPath 列（描画は bridge が優先）
    paths: list[Any] | None = None


def load_refit_config(path: Path | None = None) -> RefitConfig:
    p = path or _SNAPSHOT
    if not p.is_file():
        raise FileNotFoundError(
            f"curve_refit config missing: {p} (正本 snapshots/curve_refit.yaml)"
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    mode = str(raw.get("mode", "rdp_polyline"))
    allowed = ("rdp_polyline", "passthrough", "cubic_fit")
    if mode not in allowed:
        raise ValueError(
            f"unsupported curve_refit mode: {mode!r} (allowed: {allowed})"
        )
    kana_mode = str(raw.get("kana_mode", "passthrough"))
    if kana_mode not in allowed:
        raise ValueError(
            f"unsupported curve_refit kana_mode: {kana_mode!r} (allowed: {allowed})"
        )
    return RefitConfig(
        mode=mode,  # type: ignore[arg-type]
        epsilon_upm=float(raw.get("epsilon_upm", 1.5)),
        max_error_upm=float(raw.get("max_error_upm", 1.5)),
        max_points_soft=int(raw.get("max_points_soft", 120)),
        min_points=int(raw.get("min_points", 3)),
        enabled=bool(raw.get("enabled", True)),
        kana_mode=kana_mode,  # type: ignore[arg-type]
        cubic_max_error_upm=float(raw.get("cubic_max_error_upm", 0.5)),
        cubic_loop_max_error_upm=float(
            raw.get("cubic_loop_max_error_upm", raw.get("cubic_max_error_upm", 0.75))
        ),
        cubic_corner_deg=float(raw.get("cubic_corner_deg", 30.0)),
        cubic_max_anchors=int(raw.get("cubic_max_anchors", 48)),
    )


def _dist(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _signed_area(contour: Sequence[Point]) -> float:
    pts = _open_ring(contour)
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return 0.5 * a


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
    *,
    cubic_error_upm: float | None = None,
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

    if cfg.mode == "cubic_fit":
        # 単一輪郭 API では paths を meta に載せる（複数は refit_contours）
        from engine.curve_fit import fit_closed_contour

        err_budget = (
            cfg.cubic_max_error_upm if cubic_error_upm is None else cubic_error_upm
        )
        path, cmeta = fit_closed_contour(
            src,
            max_error_upm=err_budget,
            corner_deg=cfg.cubic_corner_deg,
            max_anchors=cfg.cubic_max_anchors,
        )
        err = float(cmeta["max_error"])
        anchors = int(cmeta["anchor_count"])
        if err > err_budget + 1e-6:
            raise ValueError(
                f"curve_refit cubic_fit gate failed: max_error={err:.4f} > "
                f"cubic_max_error_upm={err_budget}"
            )
        if anchors > cfg.cubic_max_anchors:
            raise ValueError(
                f"curve_refit cubic_fit gate failed: anchors={anchors} > "
                f"cubic_max_anchors={cfg.cubic_max_anchors}"
            )
        on = path.on_curve_points()
        meta = {
            "mode": "cubic_fit",
            "points_before": before_n,
            "points_after": anchors,
            "on_curve_after": len(on),
            "max_error": err,
            "soft_over_points": anchors > cfg.cubic_max_anchors,
            "path": path,
            **{k: cmeta[k] for k in ("corners", "n_corners", "n_segs", "n_cubic", "n_line", "anchor_count")},
        }
        return on, meta

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


def _paths_self_intersect(paths: Sequence[Any]) -> bool:
    """pathops simplify で輪郭数が増えたら自己交差とみなす。"""
    import pathops

    p = pathops.Path()
    for path in paths:
        p.moveTo(float(path.start[0]), float(path.start[1]))
        for seg in path.segs:
            if seg[0] == "L":
                p.lineTo(float(seg[1]), float(seg[2]))
            else:
                p.cubicTo(
                    float(seg[1]),
                    float(seg[2]),
                    float(seg[3]),
                    float(seg[4]),
                    float(seg[5]),
                    float(seg[6]),
                )
        p.close()
    n_before = sum(1 for _ in p.contours)
    p.simplify(fix_winding=True)
    n_after = sum(1 for _ in p.contours)
    return n_after != n_before


def refit_contours(
    contours: Sequence[Sequence[Point]],
    cfg: RefitConfig | None = None,
) -> RefitResult:
    """複数輪郭を再適合。contour 数が変わったら失敗。"""
    cfg = cfg or load_refit_config()
    out: list[list[Point]] = []
    per: list[dict[str, Any]] = []
    paths = []
    # 穴がある字だけ loop 予算（単画仮名の 0.5 ゲートを緩めない）
    cubic_budget = None
    if cfg.mode == "cubic_fit" and cfg.enabled:
        has_hole = any(_signed_area(c) < 0 for c in contours)
        cubic_budget = (
            cfg.cubic_loop_max_error_upm if has_hole else cfg.cubic_max_error_upm
        )
    for c in contours:
        simp, meta = refit_contour(c, cfg, cubic_error_upm=cubic_budget)
        out.append(simp)
        per.append(meta)
        if "path" in meta:
            paths.append(meta.pop("path"))

    if len(out) != len(contours):
        raise ValueError("curve_refit changed contour count (internal bug)")

    if (
        paths
        and not cfg.skip_combined_self_intersect
        and _paths_self_intersect(paths)
    ):
        raise ValueError("curve_refit cubic_fit gate failed: self-intersect after fit")

    # 穴構造（面積符号）不変: オンカーブ shoelace 符号列
    if paths:
        before_signs = [1 if _signed_area(c) > 0 else -1 for c in contours]
        after_signs = [
            1 if _signed_area(p.on_curve_points()) > 0 else -1 for p in paths
        ]
        if before_signs != after_signs:
            raise ValueError(
                "curve_refit cubic_fit gate failed: signed-area structure changed "
                f"{before_signs} -> {after_signs}"
            )

    pts_before = sum(m["points_before"] for m in per)
    pts_after = sum(m["points_after"] for m in per)
    worst = max((m["max_error"] for m in per), default=0.0)
    mode = cfg.mode if cfg.enabled else "disabled"
    return RefitResult(
        contours=out,
        paths=paths if paths else None,
        meta={
            "mode": mode,
            "enabled": cfg.enabled,
            "n_contours": len(out),
            "points_before": pts_before,
            "points_after": pts_after,
            "reduction_ratio": (
                (1.0 - pts_after / pts_before) if pts_before else 0.0
            ),
            "max_error": worst,
            "max_error_upm": (
                (cubic_budget if cubic_budget is not None else cfg.cubic_max_error_upm)
                if mode == "cubic_fit"
                else cfg.max_error_upm
            ),
            "any_soft_over_points": any(m["soft_over_points"] for m in per),
            "per_contour": per,
            "total_anchors": (
                sum(m.get("anchor_count", m["points_after"]) for m in per)
                if mode == "cubic_fit"
                else pts_after
            ),
            "self_intersect": False,
        },
    )
