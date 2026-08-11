"""P1-B: KANA_CURVE + 「し」スパイク8a の G1 ゲート。"""

from __future__ import annotations

import hashlib
import json

import pytest

from engine.extra_skeletons import all_characters
from engine.geometry import (
    Vec2,
    interpolate_width_keys,
    parse_cubic_chain,
    resample_by_arclength,
    sample_cubic_chain,
)
from engine.kana import KANA_GLYPH_META, kana_characters, load_kana_skeleton, skeletons_dir
from engine.params import CLASSIC, PARAM_SETS
from engine.strokes import (
    SkeletonStroke,
    StrokeKind,
    build_kana_curve,
    build_stroke,
)


def test_parse_cubic_chain_rejects_bad_counts():
    with pytest.raises(ValueError, match="3n\\+1"):
        parse_cubic_chain([Vec2(0, 0), Vec2(1, 1), Vec2(2, 2)])


def test_interpolate_width_keys_nonmonotonic():
    keys = [(0.0, 10.0), (0.5, 40.0), (1.0, 5.0)]
    assert interpolate_width_keys(0.0, keys) == pytest.approx(10.0)
    assert interpolate_width_keys(0.5, keys) == pytest.approx(40.0)
    assert interpolate_width_keys(1.0, keys) == pytest.approx(5.0)
    assert interpolate_width_keys(0.25, keys) == pytest.approx(25.0)


def test_resample_arclength_endpoints():
    samples = sample_cubic_chain(
        [Vec2(0, 0), Vec2(30, 0), Vec2(70, 0), Vec2(100, 0)], n_per_seg=20
    )
    arc = resample_by_arclength(samples, n=11)
    assert arc[0][2] == pytest.approx(0.0)
    assert arc[-1][2] == pytest.approx(1.0)
    assert abs(arc[0][0].x - 0.0) < 1.0
    assert abs(arc[-1][0].x - 100.0) < 1.0


def test_shi_yaml_loads():
    path = skeletons_dir() / "shi.yaml"
    assert path.is_file()
    gid, strokes, meta = load_kana_skeleton(path)
    assert gid == "shi"
    assert meta["unicode"] == 0x3057
    assert meta["char"] == "し"
    assert len(strokes) == 1
    assert strokes[0].kind == StrokeKind.KANA_CURVE
    assert len(strokes[0].points) == 7
    assert strokes[0].width_keys is not None


def test_shi_in_all_characters():
    chars = all_characters()
    assert "shi" in chars
    assert "shi" in KANA_GLYPH_META or kana_characters()


def test_build_kana_curve_single_contour():
    chars = kana_characters()
    stroke = chars["shi"][0]
    parts = build_kana_curve(stroke, CLASSIC)
    assert len(parts) == 1
    assert len(parts[0]) >= 8


def test_shi_solve_g1_single_contour():
    pathops = pytest.importorskip("pathops")
    from engine.join_solver import solve_glyph

    chars = all_characters()
    result = solve_glyph(chars["shi"], CLASSIC, apply_stage_a=False)
    assert result.after_cleanup == 1, (
        f"し G1: expected 1 contour, got {result.after_cleanup}"
    )


def test_shi_reproducible_contour_hash():
    pytest.importorskip("pathops")
    from engine.bridge import extract_contours_xy
    from engine.join_solver import solve_glyph

    chars = all_characters()
    r1 = solve_glyph(chars["shi"], CLASSIC, apply_stage_a=False)
    r2 = solve_glyph(all_characters()["shi"], CLASSIC, apply_stage_a=False)
    c1 = extract_contours_xy(r1.path)
    c2 = extract_contours_xy(r2.path)
    h1 = hashlib.sha256(json.dumps(c1, sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(c2, sort_keys=True).encode()).hexdigest()
    assert h1 == h2


def test_curvature_gate_rejects_hairpin():
    # 極端に尖った U ターン（半幅に対して曲率が過大）
    stroke = SkeletonStroke(
        kind=StrokeKind.KANA_CURVE,
        points=[
            Vec2(100, 100),
            Vec2(200, 100),
            Vec2(200, 110),
            Vec2(100, 110),
        ],
        width_keys=[(0.0, 40.0), (1.0, 40.0)],
    )
    with pytest.raises(ValueError, match="curvature gate"):
        build_stroke(stroke, CLASSIC)


def test_kana_meta_shi():
    chars = kana_characters()
    assert "shi" in chars
    meta = KANA_GLYPH_META["shi"]
    assert meta["name"] == "uni3057"
    assert meta["unicode"] == 0x3057
    assert meta["char"] == "し"


@pytest.mark.parametrize("params_name", ["classic", "product_r1"])
def test_shi_solve_with_param_sets(params_name):
    pytest.importorskip("pathops")
    from engine.join_solver import solve_glyph

    if params_name not in PARAM_SETS:
        pytest.skip(f"{params_name} not in PARAM_SETS")
    result = solve_glyph(
        all_characters()["shi"], PARAM_SETS[params_name], apply_stage_a=False
    )
    assert result.after_cleanup == 1
