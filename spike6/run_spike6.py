#!/usr/bin/env python3
"""spike6: Stage A join_overlap + Stage B 微小輪郭除去の検証ランナー。"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "..", "prototype")
sys.path.insert(0, os.path.abspath(PROTO))
sys.path.insert(0, HERE)

from geometry import polygon_to_svg_path  # noqa: E402
from params import PARAM_SETS  # noqa: E402

from extra_skeletons import all_characters, all_labels  # noqa: E402
from join_solver import (  # noqa: E402
    build_polys,
    count_contours,
    make_compare_svg,
    make_svg,
    path_to_svg_d,
    poly_to_path,
    solve_glyph,
    stage_a_extend,
)

OUT = os.path.join(HERE, "output")
K_VALUES = (0.10, 0.15, 0.30)
CORE = ("juu", "ni", "ei")  # 十・二・永


def overlay_d(strokes, params) -> str:
    polys = build_polys(strokes, params)
    return " ".join(polygon_to_svg_path(p) for p in polys if len(p) >= 3)


def hits_to_dict(hits) -> List[Dict[str, Any]]:
    return [
        {
            "stroke": h.stroke_index,
            "end": h.end,
            "target": h.target_index,
            "dist": round(h.distance, 3),
            "type": h.join_type,
            "proj_t": round(h.proj_t, 3),
        }
        for h in hits
    ]


def infos_to_dict(infos) -> List[Dict[str, Any]]:
    return [
        {
            "index": i.index,
            "area": round(i.area, 2),
            "bbox": [round(x, 2) for x in i.bbox],
            "removed": i.removed,
            "reason": i.reason,
        }
        for i in infos
    ]


def run_part_a(report: Dict[str, Any]) -> None:
    """A: 微小輪郭除去のみ（Stage A 無し）で 十/二/永。"""
    section: Dict[str, Any] = {}
    for pname in ("classic", "modern"):
        params = PARAM_SETS[pname]
        chars = all_characters()
        for key in CORE:
            strokes = chars[key]
            label = all_labels()[key]
            # baseline union only
            base = solve_glyph(
                strokes, params, k=0, apply_stage_a=False, cleanup_mode="none"
            )
            area_only = solve_glyph(
                strokes, params, k=0, apply_stage_a=False, cleanup_mode="area"
            )
            proximate = solve_glyph(
                strokes, params, k=0, apply_stage_a=False, cleanup_mode="proximate"
            )

            before_d = overlay_d(strokes, params)
            for tag, res in (
                ("union_only", base),
                ("area", area_only),
                ("proximate", proximate),
            ):
                path = os.path.join(OUT, f"A_{key}_{label}_{pname}_{tag}.svg")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(
                        make_svg(
                            res.svg_d,
                            f"{label} A/{tag} ({pname})",
                            f"c={res.after_cleanup} union={res.after_union}",
                        )
                    )
            cmp_path = os.path.join(OUT, f"A_{key}_{label}_{pname}_compare.svg")
            with open(cmp_path, "w", encoding="utf-8") as f:
                f.write(
                    make_compare_svg(
                        before_d,
                        proximate.svg_d,
                        f"{label} A compare ({pname})",
                        f"overlay before — c={base.before_contours}",
                        f"union+proximate — c={proximate.after_cleanup}",
                    )
                )

            section[f"{key}_{pname}"] = {
                "label": label,
                "before": base.before_contours,
                "union_only": base.after_union,
                "cleanup_area": area_only.after_cleanup,
                "cleanup_proximate": proximate.after_cleanup,
                "contour_infos_proximate": infos_to_dict(proximate.contour_infos),
                "self_intersect": proximate.self_intersect_msg,
            }
            print(
                f"[A] {label}/{pname}: before={base.before_contours} "
                f"union={base.after_union} area={area_only.after_cleanup} "
                f"prox={proximate.after_cleanup}"
            )
    report["A_micro_cleanup"] = section


def run_part_b(report: Dict[str, Any]) -> None:
    """B: Stage A join_overlap × k 感度 + 微小除去（永中心、十・二も記録）。"""
    section: Dict[str, Any] = {}
    for pname in ("classic", "modern"):
        params = PARAM_SETS[pname]
        chars = all_characters()
        for key in CORE:
            strokes = chars[key]
            label = all_labels()[key]
            k_rows = {}
            for k in K_VALUES:
                # Stage A only (union, no cleanup) and full pipeline
                a_only = solve_glyph(
                    strokes,
                    params,
                    k=k,
                    apply_stage_a=True,
                    cleanup_mode="none",
                )
                full = solve_glyph(
                    strokes,
                    params,
                    k=k,
                    apply_stage_a=True,
                    cleanup_mode="proximate",
                )
                # SVG for 永 always; others at k=0.15
                if key == "ei" or abs(k - 0.15) < 1e-9:
                    stem = f"B_{key}_{label}_{pname}_k{k:.2f}"
                    with open(
                        os.path.join(OUT, f"{stem}_stageA_union.svg"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(
                            make_svg(
                                a_only.svg_d,
                                f"{label} StageA k={k} union ({pname})",
                                f"c={a_only.after_union} hits={len(a_only.hits)} "
                                f"overlap={a_only.overlap:.2f}",
                            )
                        )
                    with open(
                        os.path.join(OUT, f"{stem}_full.svg"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(
                            make_svg(
                                full.svg_d,
                                f"{label} StageA+B k={k} ({pname})",
                                f"c={full.after_cleanup} hits={len(full.hits)}",
                            )
                        )
                    before_d = overlay_d(strokes, params)
                    with open(
                        os.path.join(OUT, f"{stem}_compare.svg"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(
                            make_compare_svg(
                                before_d,
                                full.svg_d,
                                f"{label} B compare k={k} ({pname})",
                                f"overlay — c={full.before_contours}",
                                f"A+B k={k} — c={full.after_cleanup}",
                            )
                        )

                k_rows[f"{k:.2f}"] = {
                    "overlap": round(a_only.overlap, 3),
                    "hits": hits_to_dict(a_only.hits),
                    "n_hits": len(a_only.hits),
                    "after_stageA_union": a_only.after_union,
                    "after_full": full.after_cleanup,
                    "removed": [
                        i
                        for i in infos_to_dict(full.contour_infos)
                        if i["removed"]
                    ],
                    "self_intersect_suspect": full.self_intersect_suspect,
                    "self_intersect_msg": full.self_intersect_msg,
                }
                print(
                    f"[B] {label}/{pname} k={k:.2f}: hits={len(a_only.hits)} "
                    f"union={a_only.after_union} full={full.after_cleanup} "
                    f"overlap={a_only.overlap:.2f}"
                )

            # gap diagnostics for 永: ten vs others
            gap_note = None
            if key == "ei":
                from join_solver import dist_point_to_polyline, stroke_centerline
                from strokes import StrokeKind

                ten = next(s for s in strokes if s.kind == StrokeKind.TEN)
                others = [s for s in strokes if s.kind != StrokeKind.TEN]
                gaps = []
                for ep_name, ep in (("start", ten.points[0]), ("end", ten.points[-1])):
                    for j, o in enumerate(others):
                        d, t, _ = dist_point_to_polyline(ep, stroke_centerline(o))
                        gaps.append(
                            {
                                "ten_end": ep_name,
                                "other_idx": j,
                                "kind": o.kind.value,
                                "dist": round(d, 2),
                                "proj_t": round(t, 3),
                            }
                        )
                gap_note = {
                    "ten_endpoint_gaps": gaps,
                    "min_gap": min(g["dist"] for g in gaps),
                }

            section[f"{key}_{pname}"] = {
                "label": label,
                "k_sweep": k_rows,
                "ten_gap": gap_note,
            }
    report["B_stage_a"] = section


def run_part_extra_preview(report: Dict[str, Any]) -> None:
    """追加字を k=0.15 + proximate で一度回し、期待値決めの参考にする。"""
    params = PARAM_SETS["classic"]
    chars = all_characters()
    labels = all_labels()
    preview = {}
    for key in ("ki", "hon", "nichi", "ta", "kuchi"):
        res = solve_glyph(
            chars[key], params, k=0.15, apply_stage_a=True, cleanup_mode="proximate"
        )
        path = os.path.join(OUT, f"C_preview_{key}_{labels[key]}_classic.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                make_svg(
                    res.svg_d,
                    f"{labels[key]} preview",
                    f"c={res.after_cleanup} hits={len(res.hits)}",
                )
            )
        preview[key] = {
            "label": labels[key],
            "before": res.before_contours,
            "after_union": res.after_union,
            "after_full": res.after_cleanup,
            "hits": len(res.hits),
            "areas": [
                round(i.area, 1) for i in res.contour_infos if not i.removed
            ],
        }
        print(
            f"[preview] {labels[key]}: {res.before_contours}→"
            f"{res.after_union}→{res.after_cleanup} hits={len(res.hits)}"
        )
    report["C_preview"] = preview


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    report: Dict[str, Any] = {
        "k_values": list(K_VALUES),
        "area_ratio": 0.005,
        "proximity": 8.0,
    }
    print("=== spike6 Part A: micro cleanup ===")
    run_part_a(report)
    print("=== spike6 Part B: Stage A k-sweep ===")
    run_part_b(report)
    print("=== spike6 Part C preview (extra glyphs) ===")
    run_part_extra_preview(report)

    # Expected contour targets (PLAN §3.3)
    report["expected"] = {
        "juu": 1,
        "ni": 2,
        "ei": "2 if ten isolated else 1",
    }

    # Verdict helpers
    verdicts = {}
    for pname in ("classic", "modern"):
        a = report["A_micro_cleanup"]
        b = report["B_stage_a"]
        juu_a = a[f"juu_{pname}"]["cleanup_proximate"]
        ni_a = a[f"ni_{pname}"]["cleanup_proximate"]
        ei_a = a[f"ei_{pname}"]["cleanup_proximate"]
        juu_b = b[f"juu_{pname}"]["k_sweep"]["0.15"]["after_full"]
        ni_b = b[f"ni_{pname}"]["k_sweep"]["0.15"]["after_full"]
        ei_b = b[f"ei_{pname}"]["k_sweep"]["0.15"]["after_full"]
        ei_best = min(
            row["after_full"]
            for row in b[f"ei_{pname}"]["k_sweep"].values()
        )
        verdicts[pname] = {
            "A_only_juu_ok": juu_a == 1,
            "A_only_ni_ok": ni_a == 2,
            "A_only_ei_ok": ei_a in (1, 2),
            "AB_juu_ok": juu_b == 1,
            "AB_ni_ok": ni_b == 2,
            "AB_ei_ok": ei_b in (1, 2),
            "AB_ei_best_contours": ei_best,
            "AB_ei_at_k015": ei_b,
        }
    report["verdicts"] = verdicts

    out_json = os.path.join(OUT, "spike6_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("wrote", out_json)
    print("verdicts:", json.dumps(verdicts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
