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
from engine.kana.schema import parse_gate, parse_joins
from engine.params import PARAM_SETS

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kana_fail"


@pytest.fixture(scope="module")
def pathops():
    return pytest.importorskip("pathops")


def test_schema_rejects_unknown_gate_key():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_gate("x", {"expect_contours": 1, "nope": 1})


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


@pytest.mark.parametrize("gid", ["shi", "i", "to", "tsu"])
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
