"""regression_join20.yaml を読み、全字を自動判定する pytest（P2 / 掟14）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.extra_skeletons import all_characters, all_labels
from engine.join_solver import solve_glyph
from engine.params import PARAM_SETS

HERE = Path(__file__).resolve().parent
# engine/tests → repo root (myfont/)
REPO_ROOT = HERE.parents[1]
SPEC_PATH = REPO_ROOT / "tests" / "regression_join20.yaml"


def load_spec() -> dict[str, Any]:
    if not SPEC_PATH.is_file():
        raise FileNotFoundError(
            f"掟14 正本が見つかりません: {SPEC_PATH} "
            "(expected repo-root tests/regression_join20.yaml)"
        )
    with open(SPEC_PATH, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict) or "glyphs" not in doc or "solver" not in doc:
        raise ValueError(f"invalid regression_join20.yaml: {SPEC_PATH}")
    return doc


SPEC = load_spec()
GLYPHS: list[dict[str, Any]] = SPEC["glyphs"]
SOLVER = SPEC["solver"]
PARAM_NAME = SPEC.get("params", "classic")


def _solve(glyph_id: str, params_name: str | None = None):
    chars = all_characters()
    assert glyph_id in chars, f"unknown glyph id: {glyph_id}"
    params = PARAM_SETS[params_name or PARAM_NAME]
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


def test_yaml_has_twenty_glyphs():
    assert len(GLYPHS) == 20
    ids = {g["id"] for g in GLYPHS}
    assert {"juu", "ni", "ei", "naka", "san", "kawa"}.issubset(ids)
    assert len(ids) == 20, "glyph ids must be unique"


def test_spec_path_is_repo_canonical():
    assert SPEC_PATH.is_file()
    assert SPEC_PATH.name == "regression_join20.yaml"
    assert SPEC_PATH.parent.name == "tests"
    assert (SPEC_PATH.parent.parent / "engine").is_dir()


def test_yaml_chars_match_labels_and_skeletons():
    """黄金ファイルの id/字 と骨格レジストリのずれを禁止（掟18）。"""
    labels = all_labels()
    chars = all_characters()
    for g in GLYPHS:
        gid = g["id"]
        assert gid in chars, f"missing skeleton: {gid}"
        assert gid in labels, f"missing label: {gid}"
        assert labels[gid] == g["char"], (
            f"{gid}: label {labels[gid]!r} != yaml char {g['char']!r}"
        )
        assert len(chars[gid]) >= 1


def test_all_characters_returns_independent_copies():
    a = all_characters()
    b = all_characters()
    assert a["hon"] is not b["hon"]
    a["hon"][0].points[0] = a["hon"][0].points[0].__class__(0, 0)
    assert b["hon"][0].points[0].x != 0


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
    """3 params × 20字で接合 DoD を固定（掟14）。"""
    result = _solve(glyph["id"], params_name=params_name)
    assert result.after_cleanup == int(glyph["expected_contours"]), (
        f"{params_name} {glyph['char']}({glyph['id']}): "
        f"{result.after_cleanup} != {glyph['expected_contours']}"
    )
