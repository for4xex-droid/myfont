"""regression_join.yaml を読み、全字を自動判定する pytest（P2）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.extra_skeletons import all_characters
from engine.join_solver import solve_glyph
from engine.params import PARAM_SETS

HERE = Path(__file__).resolve().parent


def load_spec() -> dict[str, Any]:
    with open(HERE / "regression_join.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


SPEC = load_spec()
GLYPHS: list[dict[str, Any]] = SPEC["glyphs"]
SOLVER = SPEC["solver"]
PARAM_NAME = SPEC.get("params", "classic")


def _solve(glyph_id: str):
    chars = all_characters()
    assert glyph_id in chars, f"unknown glyph id: {glyph_id}"
    params = PARAM_SETS[PARAM_NAME]
    return solve_glyph(
        chars[glyph_id],
        params,
        k=float(SOLVER["k"]),
        area_ratio=float(SOLVER["area_ratio"]),
        upm_area_ratio=float(SOLVER.get("upm_area_ratio", 0.0035)),
        proximity=float(SOLVER["proximity"]),
        cleanup_mode=str(SOLVER["cleanup_mode"]),
        apply_stage_a=True,
        detect_scale=float(SOLVER.get("detect_scale", 1.0)),
    )


@pytest.mark.parametrize(
    "glyph",
    GLYPHS,
    ids=[g["id"] for g in GLYPHS],
)
def test_expected_contours(glyph: dict[str, Any]):
    result = _solve(glyph["id"])
    expected = int(glyph["expected_contours"])
    actual = result.after_cleanup
    if glyph.get("known_gap") and actual != expected:
        pytest.xfail(
            f"{glyph['char']}({glyph['id']}): contours {actual} != "
            f"expected {expected} (known_gap). {glyph.get('notes', '')}"
        )
    assert actual == expected, (
        f"{glyph['char']}({glyph['id']}): contours {actual} != expected {expected}. "
        f"union={result.after_union} hits={len(result.hits)} "
        f"notes={glyph.get('notes', '')}"
    )


@pytest.mark.parametrize(
    "glyph",
    GLYPHS,
    ids=[g["id"] for g in GLYPHS],
)
def test_no_self_intersect(glyph: dict[str, Any]):
    """自己交差ゼロ（simplify ヒューリスティック）。known_gap 字も計測は行う。"""
    result = _solve(glyph["id"])
    want_clean = glyph.get("self_intersect", False) is False
    if not want_clean:
        return
    if glyph.get("known_gap") and result.self_intersect_suspect:
        pytest.xfail(
            f"{glyph['char']}: self-intersect suspect (known_gap): "
            f"{result.self_intersect_msg}"
        )
    assert not result.self_intersect_suspect, (
        f"{glyph['char']}({glyph['id']}): self-intersect suspect — "
        f"{result.self_intersect_msg}"
    )


def test_yaml_has_core_glyphs():
    ids = {g["id"] for g in GLYPHS}
    assert {"juu", "ni", "ei"}.issubset(ids)


def test_product_r1_in_param_sets():
    assert "product_r1" in PARAM_SETS
    p = PARAM_SETS["product_r1"]
    assert p.v_thickness == 110.0
    assert abs(p.v_thickness / p.h_thickness - 2.439) < 0.01


@pytest.mark.parametrize("params_name", ["classic", "modern", "product_r1"])
@pytest.mark.parametrize(
    "glyph",
    GLYPHS,
    ids=[g["id"] for g in GLYPHS],
)
def test_expected_contours_across_param_sets(params_name: str, glyph: dict[str, Any]):
    """製品候補 params でも接合 DoD を落とさない（classic 固定回帰の穴埋め）。"""
    chars = all_characters()
    params = PARAM_SETS[params_name]
    result = solve_glyph(
        chars[glyph["id"]],
        params,
        k=float(SOLVER["k"]),
        area_ratio=float(SOLVER["area_ratio"]),
        upm_area_ratio=float(SOLVER.get("upm_area_ratio", 0.0035)),
        proximity=float(SOLVER["proximity"]),
        cleanup_mode=str(SOLVER["cleanup_mode"]),
        apply_stage_a=True,
        detect_scale=float(SOLVER.get("detect_scale", 1.0)),
    )
    assert result.after_cleanup == int(glyph["expected_contours"]), (
        f"{params_name} {glyph['char']}({glyph['id']}): "
        f"{result.after_cleanup} != {glyph['expected_contours']}"
    )
