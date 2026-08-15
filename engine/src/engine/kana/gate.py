"""仮名数値ゲート（レビューループ B）。

CLI と pytest の共通コア。合否はここだけが決める。
座標: svg_y_down_legacy。方位角: atan2(-dy, dx)（0°=右・90°=上）。
接合判定は union 前の要素ポリゴン（micro-cleanup 偽グリーン回避）。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from engine.geometry import Vec2, sample_cubic_chain
from engine.kana.load import KANA_GLYPH_META, kana_characters, load_kana_skeleton
from engine.kana.schema import GateSpec, JoinSpec
from engine.params import MinchoParams, PARAM_SETS
from engine.strokes import SkeletonStroke

COORDINATE_SPACE = "svg_y_down_legacy"
BEARING_CONVENTION = "atan2(-dy,dx)"
# abut: 要素ポリゴンの bbox 距離がこれ以下なら「近接接合」とみなす（交差が理想）
ABUT_MAX_GAP_UPM = 2.0


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateReport:
    glyph_id: str
    params: str
    ok: bool
    coordinate_space: str = COORDINATE_SPACE
    bearing_convention: str = BEARING_CONVENTION
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "glyph_id": self.glyph_id,
            "params": self.params,
            "ok": self.ok,
            "coordinate_space": self.coordinate_space,
            "bearing_convention": self.bearing_convention,
            "error": self.error,
            "checks": [asdict(c) for c in self.checks],
        }


def bearing_deg(dx: float, dy: float) -> float:
    """legacy Y下の差分から画面上が正の方位角（度）。"""
    return math.degrees(math.atan2(-dy, dx))


def angle_in_sector(angle: float, lo: float, hi: float) -> bool:
    """角度が [lo, hi] に入るか（±180 ラップ対応の単純版）。"""
    a = ((angle + 180.0) % 360.0) - 180.0
    if lo <= hi:
        return lo <= a <= hi
    # ラップ（例: 170..-170）
    return a >= lo or a <= hi


def _stroke_by_id(
    strokes: Sequence[SkeletonStroke], eid: str
) -> SkeletonStroke:
    for s in strokes:
        if s.element_id == eid:
            return s
    raise KeyError(eid)


def _poly_bbox(poly: Sequence[Vec2]) -> tuple[float, float, float, float]:
    xs = [p.x for p in poly]
    ys = [p.y for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_poly(x: float, y: float, poly: Sequence[Vec2]) -> bool:
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i].x, poly[i].y
        xj, yj = poly[j].x, poly[j].y
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def _nearest_edge_dist(pt: Vec2, poly: Sequence[Vec2]) -> float:
    best = float("inf")
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ab = b - a
        l2 = ab.dot(ab)
        if l2 < 1e-12:
            d = (pt - a).length()
        else:
            t = max(0.0, min(1.0, (pt - a).dot(ab) / l2))
            d = (pt - (a + ab * t)).length()
        if d < best:
            best = d
    return best


def _tip_bearing(stroke: SkeletonStroke, end: str) -> tuple[Vec2, float]:
    samples = sample_cubic_chain(list(stroke.points), n_per_seg=40)
    if len(samples) < 2:
        raise ValueError("spine too short for tip bearing")
    if end == "exit":
        pos, tan = samples[-1]
    else:
        pos, tan = samples[0]
    if tan.length() < 1e-9:
        # フォールバック: 近傍点差分
        if end == "exit":
            a, b = samples[-2][0], samples[-1][0]
        else:
            a, b = samples[1][0], samples[0][0]
        tan = (b - a).normalized()
        pos = b if end == "exit" else a
    return pos, bearing_deg(tan.x, tan.y)


def _measure_overshoot(from_stroke: SkeletonStroke, to_poly: Sequence[Vec2]) -> float:
    """from の中心線が to に入ってから再び外へ出た場合、先端の外距離を返す。"""
    samples = sample_cubic_chain(list(from_stroke.points), n_per_seg=48)
    centerline = [p for p, _ in samples]
    if not centerline:
        return 0.0
    was_inside = False
    exited = False
    for pt in centerline:
        if _point_in_poly(pt.x, pt.y, to_poly):
            was_inside = True
        elif was_inside:
            exited = True
    tip = centerline[-1]
    if exited and not _point_in_poly(tip.x, tip.y, to_poly):
        return _nearest_edge_dist(tip, to_poly)
    return 0.0


def _element_parts(
    strokes: Sequence[SkeletonStroke], params: MinchoParams
) -> dict[str, list[list[Vec2]]]:
    """element id → build_stroke の全輪郭（リングは outer+inner）。"""
    from engine.strokes import build_stroke

    out: dict[str, list[list[Vec2]]] = {}
    for s in strokes:
        eid = s.element_id or f"_anon_{id(s)}"
        parts = build_stroke(s, params)
        if not parts:
            raise ValueError(f"element {eid}: empty outline")
        out[eid] = parts
    return out


def _outers_from_parts(
    parts_by_id: dict[str, list[list[Vec2]]],
) -> dict[str, list[Vec2]]:
    """リングは面積最大を外形代表にする（inner を接合判定に混ぜない）。"""
    from engine.geometry import _poly_abs_area

    out: dict[str, list[Vec2]] = {}
    for eid, parts in parts_by_id.items():
        out[eid] = parts[0] if len(parts) == 1 else max(parts, key=_poly_abs_area)
    return out


def _element_polys(
    strokes: Sequence[SkeletonStroke], params: MinchoParams
) -> dict[str, list[Vec2]]:
    return _outers_from_parts(_element_parts(strokes, params))


def _element_holes(
    parts_by_id: dict[str, list[list[Vec2]]],
) -> dict[str, list[list[Vec2]]]:
    """リング要素の inner（面積最大以外）。単画は空。"""
    from engine.geometry import _poly_abs_area

    out: dict[str, list[list[Vec2]]] = {}
    for eid, parts in parts_by_id.items():
        if len(parts) <= 1:
            out[eid] = []
            continue
        outer = max(parts, key=_poly_abs_area)
        out[eid] = [p for p in parts if p is not outer]
    return out


def _depth_in_holes(
    pts: Sequence[Vec2], hole_polys: Sequence[Sequence[Vec2]]
) -> float | None:
    """点が穴内なら縁までの最大深さ。未侵入なら None。"""
    worst: float | None = None
    for pt in pts:
        for hole in hole_polys:
            if len(hole) < 3:
                continue
            if _point_in_poly(pt.x, pt.y, hole):
                d = _nearest_edge_dist(pt, hole)
                if worst is None or d > worst:
                    worst = d
    return worst


def _poly_counter_pierce(
    from_poly: Sequence[Vec2], hole_polys: Sequence[Sequence[Vec2]]
) -> float | None:
    """肉付け後の外形頂点＋辺中点が穴に入った最大深さ。"""
    if not hole_polys or not from_poly:
        return None
    pts = list(from_poly)
    n = len(from_poly)
    for i in range(n):
        a = from_poly[i]
        b = from_poly[(i + 1) % n]
        pts.append(Vec2((a.x + b.x) * 0.5, (a.y + b.y) * 0.5))
    return _depth_in_holes(pts, hole_polys)


def _measure_counter_pierce(
    from_stroke: SkeletonStroke,
    hole_polys: Sequence[Sequence[Vec2]],
    from_poly: Sequence[Vec2] | None = None,
) -> float | None:
    """中心線または肉付け外形が相手の穴に入った最大深さ。未侵入なら None。

    先端だけ／中心線だけ見ると、(1) 穴横断着地 (2) 太いインクだけが穴に入る
    突き抜けを逃す。
    """
    if not hole_polys:
        return None
    samples = sample_cubic_chain(list(from_stroke.points), n_per_seg=48)
    spine_pts = [p for p, _tan in samples]
    worst = _depth_in_holes(spine_pts, hole_polys)
    ink = _poly_counter_pierce(from_poly or (), hole_polys)
    if ink is None:
        return worst
    if worst is None:
        return ink
    return max(worst, ink)


def _polys_abut(a: Sequence[Vec2], b: Sequence[Vec2], max_gap: float) -> tuple[bool, str]:
    from engine.join_solver import bbox_distance, count_contours, pathops_union, poly_to_path

    bb_a = _poly_bbox(a)
    bb_b = _poly_bbox(b)
    gap = bbox_distance(bb_a, bb_b)
    pa, pb = poly_to_path(list(a)), poly_to_path(list(b))
    united = pathops_union([pa, pb])
    n = count_contours(united)
    if n == 1:
        return True, f"union_contours=1 gap={gap:.2f}"
    if gap <= max_gap:
        return True, f"near_abut gap={gap:.2f}<={max_gap}"
    return False, f"separated union_contours={n} gap={gap:.2f}"


def run_gate_on(
    glyph_id: str,
    strokes: Sequence[SkeletonStroke],
    meta: dict[str, Any],
    params: MinchoParams,
    params_name: str = "product_r1",
    expect_contours_override: int | None = None,
) -> GateReport:
    """骨格データに対してゲートを実行。"""
    from engine.bridge import extract_contours_xy
    from engine.join_solver import bbox_distance, solve_glyph

    report = GateReport(glyph_id=glyph_id, params=params_name, ok=True)
    gate: GateSpec | None = meta.get("gate")
    joins: tuple[JoinSpec, ...] = tuple(meta.get("joins") or ())

    if gate is None:
        report.ok = False
        report.error = "gate: missing in skeleton meta (required for B)"
        report.checks.append(
            CheckResult("gate_present", False, "gate block required")
        )
        return report

    expect = (
        expect_contours_override
        if expect_contours_override is not None
        else gate.expect_contours
    )

    # --- curvature / build ---
    try:
        parts_by_id = _element_parts(strokes, params)
        element_polys = _outers_from_parts(parts_by_id)
        element_holes = _element_holes(parts_by_id)
    except ValueError as e:
        report.ok = False
        report.checks.append(
            CheckResult("curvature_or_build", False, str(e))
        )
        return report
    report.checks.append(CheckResult("curvature_or_build", True, "ok"))

    # --- solve ---
    compose = str(meta.get("compose") or "union")
    try:
        r1 = solve_glyph(
            strokes, params, apply_stage_a=False, compose=compose
        )
        r2 = solve_glyph(
            list(strokes), params, apply_stage_a=False, compose=compose
        )
    except ValueError as e:
        report.ok = False
        report.checks.append(CheckResult("solve", False, str(e)))
        return report

    # contours
    ok_c = r1.after_cleanup == expect
    report.checks.append(
        CheckResult(
            "contours",
            ok_c,
            f"got {r1.after_cleanup}, expect {expect}",
            {"got": r1.after_cleanup, "expect": expect},
        )
    )
    if not ok_c:
        report.ok = False

    # holes（負面積輪郭。Phase 0a winding 前提の solve 空間）
    if gate.expect_holes is not None:
        from engine.join_solver import polygon_signed_area

        conts = extract_contours_xy(r1.path)
        n_holes = sum(1 for c in conts if polygon_signed_area(c) < 0)
        ok_holes = n_holes == gate.expect_holes
        report.checks.append(
            CheckResult(
                "holes",
                ok_holes,
                f"got {n_holes}, expect {gate.expect_holes}",
                {"got": n_holes, "expect": gate.expect_holes},
            )
        )
        if not ok_holes:
            report.ok = False

    # reproducibility
    c1 = extract_contours_xy(r1.path)
    c2 = extract_contours_xy(r2.path)
    h1 = hashlib.sha256(json.dumps(c1, sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(c2, sort_keys=True).encode()).hexdigest()
    ok_hash = h1 == h2
    report.checks.append(
        CheckResult(
            "reproducibility",
            ok_hash,
            f"sha256={h1[:16]}…" if ok_hash else "contour hash mismatch",
            {"sha256": h1 if ok_hash else None},
        )
    )
    if not ok_hash:
        report.ok = False

    # self-intersect
    ok_si = not r1.self_intersect_suspect
    report.checks.append(
        CheckResult(
            "self_intersect",
            ok_si,
            "clean" if ok_si else r1.self_intersect_msg or "suspect",
        )
    )
    if not ok_si:
        report.ok = False

    # joins (pre-union)
    for j in joins:
        try:
            pa = element_polys[j.from_id]
            pb = element_polys[j.to_id]
        except KeyError as e:
            report.ok = False
            report.checks.append(
                CheckResult(
                    f"join:{j.from_id}->{j.to_id}",
                    False,
                    f"missing element {e}",
                )
            )
            continue
        abut_ok, detail = _polys_abut(pa, pb, ABUT_MAX_GAP_UPM)
        if j.mode == "abut":
            ok_j = abut_ok
            msg = detail
        elif j.mode in ("cross", "overlap"):
            # 跡み越え / 重ね。出力は compose:overlay のとき union しない。
            # overshoot / counter_pierce は見ない。
            ok_j = abut_ok
            msg = f"expected {j.mode}; {detail}"
        else:  # separate
            ok_j = not abut_ok
            msg = f"expected separate; {detail}"
        report.checks.append(
            CheckResult(
                f"join:{j.from_id}->{j.to_id}:{j.mode}",
                ok_j,
                msg,
            )
        )
        if not ok_j:
            report.ok = False

        # overshoot / 穴突き抜け（abut のみ。pierce は予算キー無しでも見る）
        if j.mode == "abut":
            from_stroke = _stroke_by_id(strokes, j.from_id)
            if gate.max_overshoot_upm is not None:
                over = _measure_overshoot(from_stroke, pb)
                ok_o = over <= gate.max_overshoot_upm
                report.checks.append(
                    CheckResult(
                        f"overshoot:{j.from_id}->{j.to_id}",
                        ok_o,
                        f"overshoot={over:.2f} max={gate.max_overshoot_upm}",
                        {"overshoot_upm": over, "max": gate.max_overshoot_upm},
                    )
                )
                if not ok_o:
                    report.ok = False

            # 外形 overshoot は「outer 内のまま」なので穴内を 0 と誤る。
            # 中心線が相手リングの inner に入ったら無条件 fail。
            pierce = _measure_counter_pierce(
                from_stroke,
                element_holes.get(j.to_id) or (),
                from_poly=pa,
            )
            ok_p = pierce is None
            report.checks.append(
                CheckResult(
                    f"counter_pierce:{j.from_id}->{j.to_id}",
                    ok_p,
                    "clean" if ok_p else f"tip_in_hole depth={pierce:.2f}",
                    {"depth_upm": pierce},
                )
            )
            if not ok_p:
                report.ok = False

    # bbox
    if gate.bbox is not None:
        all_pts = [pt for poly in element_polys.values() for pt in poly]
        xs = [p.x for p in all_pts]
        ys = [p.y for p in all_pts]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        aspect = w / h if h > 1e-9 else float("inf")
        bw = gate.bbox.width
        bh = gate.bbox.height
        ok_w = bw[0] <= w <= bw[1]
        ok_h = bh[0] <= h <= bh[1]
        ok_a = True
        if gate.bbox.aspect_w_over_h is not None:
            alo, ahi = gate.bbox.aspect_w_over_h
            ok_a = alo <= aspect <= ahi
        ok_bb = ok_w and ok_h and ok_a
        report.checks.append(
            CheckResult(
                "bbox",
                ok_bb,
                f"w={w:.1f} h={h:.1f} aspect={aspect:.3f}",
                {
                    "width": w,
                    "height": h,
                    "aspect_w_over_h": aspect,
                    "expect_width": list(bw),
                    "expect_height": list(bh),
                    "expect_aspect": (
                        list(gate.bbox.aspect_w_over_h)
                        if gate.bbox.aspect_w_over_h
                        else None
                    ),
                },
            )
        )
        if not ok_bb:
            report.ok = False

    # tips / bearing
    for tip in gate.tips:
        try:
            stroke = _stroke_by_id(strokes, tip.element)
            _pos, ang = _tip_bearing(stroke, tip.end)
        except (KeyError, ValueError) as e:
            report.ok = False
            report.checks.append(
                CheckResult(
                    f"tip:{tip.element}.{tip.end}",
                    False,
                    str(e),
                )
            )
            continue
        lo, hi = tip.bearing_deg
        ok_t = angle_in_sector(ang, lo, hi)
        report.checks.append(
            CheckResult(
                f"tip:{tip.element}.{tip.end}",
                ok_t,
                f"bearing={ang:.1f}° expect=[{lo},{hi}]",
                {
                    "bearing_deg": ang,
                    "expect": [lo, hi],
                    "bearing_convention": BEARING_CONVENTION,
                },
            )
        )
        if not ok_t:
            report.ok = False

    # gaps
    for gap in gate.gaps:
        try:
            pa = element_polys[gap.a]
            pb = element_polys[gap.b]
        except KeyError as e:
            report.ok = False
            report.checks.append(
                CheckResult(f"gap:{gap.a}-{gap.b}", False, f"missing {e}")
            )
            continue
        dist = bbox_distance(_poly_bbox(pa), _poly_bbox(pb))
        ok_g = gap.min_upm <= dist <= gap.max_upm
        report.checks.append(
            CheckResult(
                f"gap:{gap.a}-{gap.b}",
                ok_g,
                f"bbox_dist={dist:.1f} expect=[{gap.min_upm},{gap.max_upm}]",
                {"bbox_dist_upm": dist, "min": gap.min_upm, "max": gap.max_upm},
            )
        )
        if not ok_g:
            report.ok = False

    return report


def run_gate(
    glyph_id: str,
    params: MinchoParams | str = "product_r1",
    expect_contours_override: int | None = None,
) -> GateReport:
    """登録済み仮名 glyph に対してゲート実行。"""
    if isinstance(params, str):
        params_name = params
        if params_name not in PARAM_SETS:
            return GateReport(
                glyph_id=glyph_id,
                params=params_name,
                ok=False,
                error=f"unknown params {params_name}",
            )
        params_obj = PARAM_SETS[params_name]
    else:
        params_name = "custom"
        params_obj = params

    chars = kana_characters()
    if glyph_id not in chars:
        return GateReport(
            glyph_id=glyph_id,
            params=params_name,
            ok=False,
            error=f"unknown glyph {glyph_id}",
        )
    meta = KANA_GLYPH_META[glyph_id]
    return run_gate_on(
        glyph_id,
        chars[glyph_id],
        meta,
        params_obj,
        params_name=params_name,
        expect_contours_override=expect_contours_override,
    )


def run_gate_path(
    path,
    params: MinchoParams | str = "product_r1",
    expect_contours_override: int | None = None,
) -> GateReport:
    """任意 YAML パス（失敗フィクスチャ用）。"""
    if isinstance(params, str):
        params_name = params
        params_obj = PARAM_SETS[params_name]
    else:
        params_name = "custom"
        params_obj = params
    gid, strokes, meta = load_kana_skeleton(path)
    return run_gate_on(
        gid,
        strokes,
        meta,
        params_obj,
        params_name=params_name,
        expect_contours_override=expect_contours_override,
    )
