"""pathops fix_winding 規約カナリア（Phase 0a / F14）。

外形=正・穴=負が入力巻きに依存せず決定的であること。
pathops 更新で規約が変わったら一括 reverse の前提を再検証する。
"""

from __future__ import annotations

import pathops
import pytest
from pathops import Path, PathVerb

from engine.join_solver import (
    count_contours,
    polygon_signed_area,
    remove_micro_contours,
    split_contours,
)


def _signed_areas(path: Path) -> list[float]:
    out: list[float] = []
    for c in split_contours(path):
        pts: list[tuple[float, float]] = []
        for verb, p in c:
            if verb in (PathVerb.MOVE, PathVerb.LINE):
                pts.append((float(p[0][0]), float(p[0][1])))
        out.append(polygon_signed_area(pts))
    return out


def _ring(outer_ccw: bool, inner_ccw: bool) -> Path:
    o = [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0)]
    i = [(300.0, 300.0), (700.0, 300.0), (700.0, 700.0), (300.0, 700.0)]
    if not outer_ccw:
        o = list(reversed(o))
    if not inner_ccw:
        i = list(reversed(i))
    p = Path()
    p.moveTo(*o[0])
    for pt in o[1:]:
        p.lineTo(*pt)
    p.close()
    p.moveTo(*i[0])
    for pt in i[1:]:
        p.lineTo(*pt)
    p.close()
    return p


@pytest.mark.parametrize("outer_ccw", [True, False])
@pytest.mark.parametrize("inner_ccw", [True, False])
def test_fix_winding_convention_deterministic(outer_ccw: bool, inner_ccw: bool):
    """4通り入力 → 外形正・穴負（相対巻きが逆のときのみ穴が残る）。"""
    simp = pathops.simplify(_ring(outer_ccw, inner_ccw), fix_winding=True)
    areas = _signed_areas(simp)
    opposite = outer_ccw != inner_ccw
    if opposite:
        assert count_contours(simp) == 2
        assert len(areas) == 2
        # 大きい方が外形=正、小さい方が穴=負
        areas_sorted = sorted(areas, key=abs, reverse=True)
        assert areas_sorted[0] > 0
        assert areas_sorted[1] < 0
    else:
        # 同巻き入れ子は nonzero で単一輪郭に融合
        assert count_contours(simp) == 1
        assert areas[0] > 0


def test_micro_cleanup_keeps_significant_nested_hole():
    """入れ子穴で保護床以上（≈3000）かつ微小除去床未満なら残す。"""
    p = Path()
    p.moveTo(0, 0)
    p.lineTo(1000, 0)
    p.lineTo(1000, 1000)
    p.lineTo(0, 1000)
    p.close()
    # 55×55≈3025: 端物くず帯(≲2414)より上・除去床(3500)より下
    p.moveTo(100, 100)
    p.lineTo(100, 155)
    p.lineTo(155, 155)
    p.lineTo(155, 100)
    p.close()
    p = pathops.simplify(p, fix_winding=True)
    assert any(a < 0 for a in _signed_areas(p))

    cleaned, infos = remove_micro_contours(p)
    assert any(a < 0 for a in _signed_areas(cleaned)), "hole was removed"
    kept = [i for i in infos if i.reason.startswith("kept_hole")]
    assert kept
    assert all(not i.removed for i in kept)


def test_micro_cleanup_still_removes_nested_scrap_hole():
    """入れ子でも保護床未満の端物巻きくずは除去する。"""
    p = Path()
    p.moveTo(0, 0)
    p.lineTo(1000, 0)
    p.lineTo(1000, 1000)
    p.lineTo(0, 1000)
    p.close()
    # 20×20=400 < hole_keep(2500)
    p.moveTo(100, 100)
    p.lineTo(100, 120)
    p.lineTo(120, 120)
    p.lineTo(120, 100)
    p.close()
    p = pathops.simplify(p, fix_winding=True)
    cleaned, infos = remove_micro_contours(p)
    assert count_contours(cleaned) == 1
    assert any(i.removed for i in infos if i.signed_area < 0)
