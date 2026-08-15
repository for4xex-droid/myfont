"""レビューループ B: 数値ゲート v2。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.kana import (
    KANA_GLYPH_META,
    load_kana_skeleton,
    run_gate,
    run_gate_path,
    skeletons_dir,
)
from engine.kana.schema import parse_gate, parse_joins, parse_loop_closure
from engine.params import PARAM_SETS

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kana_fail"


@pytest.fixture(scope="module")
def pathops():
    return pytest.importorskip("pathops")


def test_schema_rejects_unknown_gate_key():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_gate("x", {"expect_contours": 1, "nope": 1})


def test_schema_parses_expect_holes():
    g = parse_gate("x", {"expect_contours": 2, "expect_holes": 1})
    assert g.expect_holes == 1


def test_schema_rejects_unknown_loop_key():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_loop_closure("x", {"overlap_upm": 2, "nope": 1})


def test_schema_requires_expect_contours():
    with pytest.raises(ValueError, match="expect_contours"):
        parse_gate("x", {"bbox": {"width": [1, 2], "height": [1, 2]}})


def test_schema_join_requires_mode():
    with pytest.raises(ValueError, match="mode"):
        parse_joins("x", [{"from": "a", "to": "b"}])


def test_loader_keeps_element_id_and_gate():
    gid, strokes, meta = load_kana_skeleton(skeletons_dir() / "to.yaml")
    assert gid == "to"
    assert [s.element_id for s in strokes] == ["main", "ten"]
    assert meta["gate"] is not None
    assert meta["gate"].expect_contours == 1
    assert len(meta["joins"]) == 1
    assert meta["joins"][0].mode == "abut"


def test_loader_rejects_unknown_top_level(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        yaml.dump(
            {
                "char": "し",
                "glyph_id": "bad",
                "unicode": 0x3057,
                "elements": [
                    {
                        "id": "main",
                        "spine": [[0, 0], [1, 0], [2, 0], [3, 0]],
                        "width": [{"s": 0.0, "hw": 1}, {"s": 1.0, "hw": 1}],
                        "ends": {"entry": "none", "exit": "none"},
                    }
                ],
                "gate": {"expect_contours": 1},
                "extra_junk": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown keys"):
        load_kana_skeleton(p)


@pytest.mark.parametrize("gid", ["shi", "i", "to", "tsu", "ku", "no"])
def test_current_glyphs_gate_green(gid: str, pathops):
    report = run_gate(gid, params="product_r1")
    assert report.ok, report.to_dict()
    assert report.coordinate_space == "svg_y_down_legacy"
    assert report.bearing_convention == "atan2(-dy,dx)"
    assert KANA_GLYPH_META[gid]["gate"] is not None


def test_fail_float(pathops):
    report = run_gate_path(FIXTURES / "to_float.yaml", params="product_r1")
    assert not report.ok
    names = {c.name: c for c in report.checks}
    assert names["join:ten->main:abut"].ok is False


def test_fail_pierce(pathops):
    report = run_gate_path(FIXTURES / "to_pierce.yaml", params="product_r1")
    assert not report.ok
    overs = [c for c in report.checks if c.name.startswith("overshoot:")]
    assert overs and overs[0].ok is False


def test_no_counter_pierce_clean(pathops):
    """現行「の」テールはリング本体上。穴内にいない。"""
    report = run_gate("no", params="product_r1")
    assert report.ok, report.to_dict()
    pierces = [c for c in report.checks if c.name.startswith("counter_pierce:")]
    assert pierces and pierces[0].ok is True
    assert pierces[0].data.get("depth_upm") is None


def test_no_tail_into_hole_fails_counter_pierce(pathops):
    """テール先端をカウンターへ入れたら overshoot=0 でも counter_pierce が赤。"""
    from engine.geometry import Vec2
    from engine.kana.gate import run_gate_on
    from engine.strokes import SkeletonStroke

    gid, strokes, meta = load_kana_skeleton(skeletons_dir() / "no.yaml")
    moved = []
    for s in strokes:
        if s.element_id == "tail":
            pts = list(s.points)
            pts[-1] = Vec2(580.0, 560.0)
            moved.append(
                SkeletonStroke(
                    kind=s.kind,
                    points=pts,
                    start_tag=s.start_tag,
                    end_tag=s.end_tag,
                    width_keys=s.width_keys,
                    element_id=s.element_id,
                    loop_closed=s.loop_closed,
                    loop_overlap_upm=s.loop_overlap_upm,
                    loop_join_angle_deg=s.loop_join_angle_deg,
                )
            )
        else:
            moved.append(s)
    report = run_gate_on(
        gid, moved, meta, PARAM_SETS["product_r1"], params_name="product_r1"
    )
    assert not report.ok
    pierces = [c for c in report.checks if c.name.startswith("counter_pierce:")]
    assert pierces and pierces[0].ok is False
    overs = [c for c in report.checks if c.name.startswith("overshoot:")]
    assert overs and overs[0].ok is True


def test_counter_pierce_scans_midline_not_just_tip():
    """先端は穴の外、中心線が穴を横断 → 深さ > 0。"""
    from engine.geometry import Vec2
    from engine.kana.gate import _measure_counter_pierce
    from engine.strokes import SkeletonStroke, StrokeKind

    hole = [
        Vec2(400.0, 400.0),
        Vec2(700.0, 400.0),
        Vec2(700.0, 700.0),
        Vec2(400.0, 700.0),
    ]
    stroke = SkeletonStroke(
        kind=StrokeKind.KANA_CURVE,
        points=[
            Vec2(100.0, 550.0),
            Vec2(300.0, 550.0),
            Vec2(800.0, 550.0),
            Vec2(900.0, 550.0),
        ],
        element_id="tail",
    )
    depth = _measure_counter_pierce(stroke, [hole])
    assert depth is not None and depth > 0.0


def test_counter_pierce_catches_fat_ink_not_just_spine():
    """中心線は穴の外、肉付け外形だけが穴に入る。"""
    from engine.geometry import Vec2
    from engine.kana.gate import _measure_counter_pierce
    from engine.strokes import SkeletonStroke, StrokeKind

    hole = [
        Vec2(400.0, 400.0),
        Vec2(700.0, 400.0),
        Vec2(700.0, 700.0),
        Vec2(400.0, 700.0),
    ]
    stroke = SkeletonStroke(
        kind=StrokeKind.KANA_CURVE,
        points=[
            Vec2(100.0, 300.0),
            Vec2(300.0, 300.0),
            Vec2(600.0, 300.0),
            Vec2(900.0, 300.0),
        ],
        element_id="tail",
    )
    assert _measure_counter_pierce(stroke, [hole]) is None
    fat = [
        Vec2(100.0, 250.0),
        Vec2(900.0, 250.0),
        Vec2(900.0, 480.0),
        Vec2(100.0, 480.0),
    ]
    depth = _measure_counter_pierce(stroke, [hole], from_poly=fat)
    assert depth is not None and depth > 0.0


def test_fail_mirror(pathops):
    report = run_gate_path(FIXTURES / "shi_mirror.yaml", params="product_r1")
    assert not report.ok
    tips = [c for c in report.checks if c.name.startswith("tip:")]
    assert tips and tips[0].ok is False


def test_to_separated_skeleton_fails_join(pathops):
    """現行 to の ten を左へずらした分離骨格 → abut FAIL。"""
    gid, strokes, meta = load_kana_skeleton(skeletons_dir() / "to.yaml")
    # ten を大きく左へ平行移動
    from engine.geometry import Vec2
    from engine.strokes import SkeletonStroke

    moved = []
    for s in strokes:
        if s.element_id == "ten":
            pts = [Vec2(p.x - 250, p.y) for p in s.points]
            moved.append(
                SkeletonStroke(
                    kind=s.kind,
                    points=pts,
                    start_tag=s.start_tag,
                    end_tag=s.end_tag,
                    width_keys=s.width_keys,
                    element_id=s.element_id,
                )
            )
        else:
            moved.append(s)
    from engine.kana.gate import run_gate_on

    report = run_gate_on(
        gid, moved, meta, PARAM_SETS["product_r1"], params_name="product_r1"
    )
    assert not report.ok
    join_checks = [c for c in report.checks if c.name.startswith("join:")]
    assert join_checks and join_checks[0].ok is False
