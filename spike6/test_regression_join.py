"""regression_join.yaml を読み、全字を自動判定する pytest。"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(HERE, "..", "prototype")
sys.path.insert(0, os.path.abspath(PROTO))
sys.path.insert(0, HERE)

from extra_skeletons import all_characters  # noqa: E402
from join_solver import solve_glyph  # noqa: E402
from params import PARAM_SETS  # noqa: E402


def load_spec() -> Dict[str, Any]:
    path = os.path.join(HERE, "regression_join.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


SPEC = load_spec()
GLYPHS: List[Dict[str, Any]] = SPEC["glyphs"]
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
        upm_area_ratio=float(SOLVER.get("upm_area_ratio", 0.0008)),
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
def test_expected_contours(glyph: Dict[str, Any]):
    result = _solve(glyph["id"])
    expected = int(glyph["expected_contours"])
    actual = result.after_cleanup
    if glyph.get("known_gap"):
        if actual != expected:
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
def test_no_self_intersect(glyph: Dict[str, Any]):
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
