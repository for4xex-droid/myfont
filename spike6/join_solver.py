"""Stage A (join_overlap) + Stage B (union + 微小輪郭除去) のスパイク実装。"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from pathops import Path, PathVerb, simplify, union

from geometry import Vec2
from params import MinchoParams
from strokes import SkeletonStroke, StrokeKind, build_stroke


UPM = 1000


# ---------------------------------------------------------------------------
# pathops helpers
# ---------------------------------------------------------------------------


def poly_to_path(poly: Sequence[Vec2]) -> Path:
    p = Path()
    if len(poly) < 3:
        return p
    pts = list(poly)
    if pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    if len(pts) < 3:
        return p
    p.moveTo(pts[0].x, pts[0].y)
    for pt in pts[1:]:
        p.lineTo(pt.x, pt.y)
    p.close()
    return p


def count_contours(path: Path) -> int:
    return sum(1 for v, _ in path if v == PathVerb.MOVE)


def pathops_union(paths: Sequence[Path]) -> Path:
    out = Path()
    union(list(paths), out.getPen())
    return out


def path_to_svg_d(path: Path, precision: int = 2) -> str:
    fmt = f"{{:.{precision}f}}"

    def _fmt_pts(pts) -> List[str]:
        out: List[str] = []
        for pt in pts:
            out.append(fmt.format(pt[0]))
            out.append(fmt.format(pt[1]))
        return out

    parts: List[str] = []
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            xy = _fmt_pts(pts)
            parts.append(f"M {xy[0]} {xy[1]}")
        elif verb == PathVerb.LINE:
            xy = _fmt_pts(pts)
            parts.append(f"L {xy[0]} {xy[1]}")
        elif verb == PathVerb.QUAD:
            xy = _fmt_pts(pts)
            parts.append(f"Q {xy[0]} {xy[1]} {xy[2]} {xy[3]}")
        elif verb == PathVerb.CUBIC:
            xy = _fmt_pts(pts)
            parts.append(
                f"C {xy[0]} {xy[1]} {xy[2]} {xy[3]} {xy[4]} {xy[5]}"
            )
        elif verb == PathVerb.CLOSE:
            parts.append("Z")
    return " ".join(parts)


def split_contours(path: Path) -> List[Path]:
    """複合 Path を contour 単位の Path に分割。"""
    contours: List[Path] = []
    cur: Optional[Path] = None
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            if cur is not None:
                contours.append(cur)
            cur = Path()
            cur.moveTo(pts[0][0], pts[0][1])
        elif cur is None:
            continue
        elif verb == PathVerb.LINE:
            cur.lineTo(pts[0][0], pts[0][1])
        elif verb == PathVerb.QUAD:
            cur.qCurveTo(pts[0][0], pts[0][1], pts[1][0], pts[1][1])
        elif verb == PathVerb.CUBIC:
            cur.curveTo(
                pts[0][0], pts[0][1],
                pts[1][0], pts[1][1],
                pts[2][0], pts[2][1],
            )
        elif verb == PathVerb.CLOSE:
            cur.close()
    if cur is not None:
        contours.append(cur)
    return contours


def contour_points(path: Path) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for verb, p in path:
        if verb == PathVerb.MOVE:
            pts.append((p[0][0], p[0][1]))
        elif verb == PathVerb.LINE:
            pts.append((p[0][0], p[0][1]))
        elif verb == PathVerb.QUAD:
            pts.append((p[1][0], p[1][1]))
        elif verb == PathVerb.CUBIC:
            pts.append((p[2][0], p[2][1]))
    return pts


def polygon_area(pts: Sequence[Tuple[float, float]]) -> float:
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def contour_bbox(pts: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def bbox_distance(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> float:
    """2つの軸揃え bbox 間の距離（重なれば 0）。"""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(0.0, max(ax0 - bx1, bx0 - ax1))
    dy = max(0.0, max(ay0 - by1, by0 - ay1))
    return math.hypot(dx, dy)


def check_self_intersect_heuristic(path: Path) -> Tuple[bool, str]:
    """simplify 差分ヒューリスティック（pathops に明示 API 無し）。"""
    try:
        before_c = count_contours(path)
        before_v = sum(1 for _ in path)
        simplified = simplify(path, fix_winding=True)
        after_c = count_contours(simplified)
        after_v = sum(1 for _ in simplified)
        changed = (before_c != after_c) or (abs(before_v - after_v) > 2)
        return changed, (
            f"simplify: contours {before_c}->{after_c}, "
            f"verbs {before_v}->{after_v}, changed={changed}"
        )
    except Exception as e:
        return True, f"simplify error: {e}"


# ---------------------------------------------------------------------------
# Stage A: T字接続検出 + join_overlap 延長
# ---------------------------------------------------------------------------


@dataclass
class JoinHit:
    stroke_index: int
    end: str  # "start" | "end"
    target_index: int
    distance: float
    join_type: str  # "T" | "corner"
    proj_t: float


def dist_point_to_polyline(
    p: Vec2, points: Sequence[Vec2]
) -> Tuple[float, float, Vec2]:
    """点→折れ線の最短距離、(距離, 投影パラメータ概算 t_along, 投影点)。"""
    best_d = float("inf")
    best_t = 0.0
    best_proj = points[0]
    total = 0.0
    seg_lens = []
    for i in range(len(points) - 1):
        seg_lens.append((points[i + 1] - points[i]).length())
    length_sum = sum(seg_lens) or 1.0
    acc = 0.0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        ab = b - a
        L2 = ab.dot(ab)
        if L2 < 1e-12:
            proj = a
            t_local = 0.0
            d = (p - a).length()
        else:
            t_local = max(0.0, min(1.0, (p - a).dot(ab) / L2))
            proj = a + ab * t_local
            d = (p - proj).length()
        if d < best_d:
            best_d = d
            best_t = (acc + t_local * seg_lens[i]) / length_sum
            best_proj = proj
        acc += seg_lens[i]
    return best_d, best_t, best_proj


def stroke_centerline(stroke: SkeletonStroke) -> List[Vec2]:
    return list(stroke.points)


def stroke_thickness(stroke: SkeletonStroke, params: MinchoParams) -> float:
    if stroke.thickness is not None:
        return stroke.thickness
    if stroke.kind == StrokeKind.HORIZONTAL:
        return params.h_thickness
    if stroke.kind == StrokeKind.VERTICAL:
        return params.v_thickness
    if stroke.kind == StrokeKind.LEFT_HARA:
        return params.left_hara_root
    if stroke.kind == StrokeKind.RIGHT_HARA:
        return params.right_hara_max
    if stroke.kind == StrokeKind.TEN:
        return params.ten_width
    return params.h_thickness


def join_overlap_amount(params: MinchoParams, k: float) -> float:
    return k * min(params.h_thickness, params.v_thickness)


def detect_t_joins(
    strokes: Sequence[SkeletonStroke],
    params: MinchoParams,
    detect_radius: float,
    skip_ten_as_source: bool = True,
) -> List[JoinHit]:
    """
    端点が他ストローク中心線の近傍にある接続を検出。
    - 投影 t が (0.08, 0.92) 内 → T字
    - 端点付近 → corner（角）
    TEN をソースにしない（意図的非接触の点画を融合対象にしない）。
    """
    hits: List[JoinHit] = []
    centers = [stroke_centerline(s) for s in strokes]
    for i, s in enumerate(strokes):
        if skip_ten_as_source and s.kind == StrokeKind.TEN:
            continue
        pts = centers[i]
        if len(pts) < 2:
            continue
        for end_name, ep in (("start", pts[0]), ("end", pts[-1])):
            best: Optional[JoinHit] = None
            for j, tpts in enumerate(centers):
                if i == j or len(tpts) < 2:
                    continue
                # TEN への食い込み検出は許可（点に刺さる画）するが、
                # TEN 自体はソース延長しない。
                d, t, _ = dist_point_to_polyline(ep, tpts)
                if d > detect_radius:
                    continue
                jtype = "T" if 0.08 < t < 0.92 else "corner"
                cand = JoinHit(i, end_name, j, d, jtype, t)
                if best is None or cand.distance < best.distance:
                    best = cand
            if best is not None:
                hits.append(best)
    return hits


def apply_join_overlap(
    strokes: Sequence[SkeletonStroke],
    hits: Sequence[JoinHit],
    overlap: float,
) -> List[SkeletonStroke]:
    """検出した端点を、自ストローク中心線方向へ overlap だけ延長。"""
    out = [copy.deepcopy(s) for s in strokes]
    # 同じ端点に複数ヒットがある場合は最短距離のみ（detect 側で1件）
    for hit in hits:
        s = out[hit.stroke_index]
        pts = list(s.points)
        if len(pts) < 2:
            continue
        if hit.end == "start":
            # 開始点を進行方向の逆へ延長
            tan = (pts[1] - pts[0]).normalized()
            if tan.length() < 1e-9:
                continue
            pts[0] = pts[0] - tan * overlap
        else:
            tan = (pts[-1] - pts[-2]).normalized()
            if tan.length() < 1e-9:
                continue
            pts[-1] = pts[-1] + tan * overlap
        s.points = pts
        out[hit.stroke_index] = s
    return out


def stage_a_extend(
    strokes: Sequence[SkeletonStroke],
    params: MinchoParams,
    k: float,
    detect_scale: float = 1.0,
) -> Tuple[List[SkeletonStroke], List[JoinHit], float]:
    """
    Stage A: join_overlap = k * min(h,v) で T/角接続端点を延長。
    detect_radius = detect_scale * max(join_overlap, 0.5 * min(h,v))
    """
    overlap = join_overlap_amount(params, k)
    detect_radius = detect_scale * max(overlap, 0.5 * min(params.h_thickness, params.v_thickness))
    hits = detect_t_joins(strokes, params, detect_radius)
    extended = apply_join_overlap(strokes, hits, overlap)
    return extended, hits, overlap


# ---------------------------------------------------------------------------
# Stage B: union + 微小輪郭除去
# ---------------------------------------------------------------------------


@dataclass
class ContourInfo:
    index: int
    area: float
    bbox: Tuple[float, float, float, float]
    path: Path
    removed: bool = False
    reason: str = ""


@dataclass
class SolveResult:
    before_contours: int
    after_union: int
    after_cleanup: int
    path: Path
    contour_infos: List[ContourInfo] = field(default_factory=list)
    hits: List[JoinHit] = field(default_factory=list)
    overlap: float = 0.0
    self_intersect_suspect: bool = False
    self_intersect_msg: str = ""
    svg_d: str = ""


def micro_area_threshold(
    total_ink: float,
    area_ratio: float = 0.005,
    upm_area_ratio: float = 0.0008,
) -> float:
    """
    微小輪郭の面積閾値。

    - ink 比 (area_ratio * total_ink): PLAN §3.3 の例（0.5%）
    - UPM² 比 (upm_area_ratio * UPM²): 打ち込み島が ink 比だけだと残るケースの床
      （classic「二」の島 ≈420 は ink0.5%≈300 を超える → UPM² 0.08%=800 で捕捉）
    """
    return max(area_ratio * total_ink, upm_area_ratio * (UPM * UPM), 50.0)


def remove_micro_contours(
    path: Path,
    area_ratio: float = 0.005,
    upm_area_ratio: float = 0.0008,
    proximity: float = 8.0,
    mode: str = "proximate",
) -> Tuple[Path, List[ContourInfo]]:
    """
    union 後の微小輪郭除去。

    mode:
      - "area": 面積閾値未満を除去
      - "proximate": 面積閾値未満かつ、より大きい輪郭に重なる/近接するもののみ除去
      - "none": 除去しない
    """
    contours = split_contours(path)
    infos: List[ContourInfo] = []
    for i, c in enumerate(contours):
        pts = contour_points(c)
        area = polygon_area(pts)
        bb = contour_bbox(pts) if pts else (0, 0, 0, 0)
        infos.append(ContourInfo(i, area, bb, c))

    total_ink = sum(inf.area for inf in infos) or 1.0
    area_cut = micro_area_threshold(total_ink, area_ratio, upm_area_ratio)

    if mode == "none":
        return path, infos

    keep: List[Path] = []
    for inf in infos:
        if inf.area >= area_cut:
            keep.append(inf.path)
            continue
        if mode == "area":
            inf.removed = True
            inf.reason = f"area<{area_cut:.1f}"
            continue
        # proximate: 大きい輪郭に近接/重なる場合のみ除去（孤立した意図的小片は残す）
        near_large = False
        for other in infos:
            if other.index == inf.index:
                continue
            if other.area < area_cut:
                continue
            if bbox_distance(inf.bbox, other.bbox) <= proximity:
                near_large = True
                break
        if near_large:
            inf.removed = True
            inf.reason = f"micro+proximate(d<={proximity},cut={area_cut:.0f})"
        else:
            keep.append(inf.path)
            inf.reason = "kept_isolated_small"

    if not keep:
        # 全除去は危険 → 最大面積を残す
        biggest = max(infos, key=lambda x: x.area)
        for inf in infos:
            inf.removed = inf.index != biggest.index
            if inf.removed:
                inf.reason = "fallback_keep_largest"
        return biggest.path, infos

    if len(keep) == 1:
        return keep[0], infos
    merged = pathops_union(keep)
    try:
        merged = simplify(merged, fix_winding=True)
    except Exception:
        pass
    return merged, infos


def build_polys(
    strokes: Sequence[SkeletonStroke], params: MinchoParams
) -> List[List[Vec2]]:
    polys: List[List[Vec2]] = []
    for s in strokes:
        polys.extend(build_stroke(s, params))
    return polys


def solve_glyph(
    strokes: Sequence[SkeletonStroke],
    params: MinchoParams,
    k: float = 0.15,
    area_ratio: float = 0.005,
    upm_area_ratio: float = 0.0008,
    proximity: float = 8.0,
    cleanup_mode: str = "proximate",
    apply_stage_a: bool = True,
    detect_scale: float = 1.0,
) -> SolveResult:
    hits: List[JoinHit] = []
    overlap = 0.0
    work = list(strokes)
    if apply_stage_a and k > 0:
        work, hits, overlap = stage_a_extend(work, params, k, detect_scale=detect_scale)

    polys = build_polys(work, params)
    paths = [poly_to_path(p) for p in polys if len(p) >= 3]
    paths = [p for p in paths if count_contours(p) > 0]
    before = sum(count_contours(p) for p in paths)

    united = pathops_union(paths)
    try:
        united = simplify(united, fix_winding=True)
    except Exception:
        pass
    after_union = count_contours(united)

    cleaned, infos = remove_micro_contours(
        united,
        area_ratio=area_ratio,
        upm_area_ratio=upm_area_ratio,
        proximity=proximity,
        mode=cleanup_mode,
    )
    after_cleanup = count_contours(cleaned)
    si, si_msg = check_self_intersect_heuristic(cleaned)

    return SolveResult(
        before_contours=before,
        after_union=after_union,
        after_cleanup=after_cleanup,
        path=cleaned,
        contour_infos=infos,
        hits=hits,
        overlap=overlap,
        self_intersect_suspect=si,
        self_intersect_msg=si_msg,
        svg_d=path_to_svg_d(cleaned),
    )


def make_svg(path_d: str, title: str, note: str = "") -> str:
    note_xml = (
        f"\n  <text x='20' y='980' font-size='16' fill='#666'>{note}</text>"
        if note
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {UPM} {UPM}"
     width="{UPM}" height="{UPM}">
  <title>{title}</title>
  <rect x="0" y="0" width="{UPM}" height="{UPM}" fill="none" stroke="#ddd" stroke-width="1"/>
  <path d="{path_d}" fill="#000000" fill-rule="nonzero" stroke="none"/>{note_xml}
</svg>
"""


def make_compare_svg(
    before_d: str,
    after_d: str,
    title: str,
    before_note: str,
    after_note: str,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2100 1100" width="2100" height="1100">
  <title>{title}</title>
  <text x="20" y="40" font-size="26" fill="#222">{before_note}</text>
  <text x="1120" y="40" font-size="26" fill="#222">{after_note}</text>
  <g transform="translate(50,80)">
    <rect x="0" y="0" width="1000" height="1000" fill="#fafafa" stroke="#ccc"/>
    <path d="{before_d}" fill="#000" fill-rule="nonzero"/>
  </g>
  <g transform="translate(1100,80)">
    <rect x="0" y="0" width="1000" height="1000" fill="#fafafa" stroke="#ccc"/>
    <path d="{after_d}" fill="#000" fill-rule="nonzero"/>
  </g>
</svg>
"""
