"""掟1（座標方針）・掟16（params snapshot）・境界入力の回帰。"""

from __future__ import annotations

from dataclasses import asdict, fields

import pytest
import yaml

from engine.extra_skeletons import all_characters
from engine.geometry import (
    COORDINATE_SPACE,
    UPM,
    Vec2,
    polygon_to_svg_path,
    to_font_y,
    to_svg_y,
    y_for_font,
    y_for_svg,
)
from engine.join_solver import make_svg, solve_glyph
from engine.params import CLASSIC, PRODUCT_R1, load_params_snapshot
from engine.skeletons import CHARACTERS


def test_coordinate_space_is_documented_legacy():
    assert COORDINATE_SPACE == "svg_y_down_legacy"


def test_to_svg_y_roundtrip():
    assert to_svg_y(200) == 800
    assert to_font_y(800) == 200
    assert to_svg_y(to_font_y(123.5)) == 123.5


def test_y_for_svg_identity_in_legacy():
    assert y_for_svg(340) == 340
    assert y_for_font(340) == to_font_y(340)


def test_skeleton_vertical_top_has_lower_y_in_legacy():
    juu = CHARACTERS["juu"]
    vert = next(s for s in juu if s.kind.value == "vertical")
    top, bot = vert.points[0], vert.points[1]
    assert top.y < bot.y, "legacy SVG-Y: 縦画は上→下（Y小→Y大）"


def test_polygon_svg_uses_internal_y_in_legacy():
    d = polygon_to_svg_path([Vec2(0, 0), Vec2(10, 0), Vec2(10, 10)])
    assert "M 0.00 0.00" in d
    assert str(UPM) not in d.split()[2]  # 先頭点が反転されていない


def test_product_r1_loads_from_yaml():
    loaded = load_params_snapshot("product_r1")
    assert loaded == PRODUCT_R1
    assert loaded.v_thickness == 110.0


def test_mix_k1_is_lighter_than_product_r1():
    k1 = load_params_snapshot("mix_k1")
    assert k1.v_thickness < PRODUCT_R1.v_thickness
    assert k1.h_thickness > PRODUCT_R1.h_thickness
    assert k1.uroko_height < PRODUCT_R1.uroko_height
    assert k1.v_thickness / k1.h_thickness < 1.5


def test_product_r1_repo_and_package_snapshots_match():
    """engine/params とパッケージ内 snapshots の二重配備がズレないこと。"""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1] / "params" / "product_r1.yaml"
    pkg = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "engine"
        / "snapshots"
        / "product_r1.yaml"
    )
    assert repo.is_file() and pkg.is_file()
    assert repo.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")


def test_params_snapshot_rejects_traversal():
    with pytest.raises(ValueError):
        load_params_snapshot("../product_r1")


def test_solve_empty_strokes():
    result = solve_glyph([], CLASSIC)
    assert result.after_cleanup == 0
    assert result.before_contours == 0


def test_unknown_cleanup_mode_raises():
    with pytest.raises(ValueError, match="unknown cleanup mode"):
        solve_glyph(all_characters()["ni"], CLASSIC, cleanup_mode="bogus")


def test_load_params_coerces_numeric_strings(tmp_path):
    params = asdict(PRODUCT_R1)
    params["h_thickness"] = "45.0"
    params["v_thickness"] = "110"
    doc = {"snapshot_id": "tmp", "params": params}
    path = tmp_path / "tmp.yaml"
    path.write_text(yaml.dump(doc), encoding="utf-8")
    loaded = load_params_snapshot("tmp", params_dir=tmp_path)
    assert isinstance(loaded.h_thickness, float)
    assert loaded.v_thickness == 110.0
    assert {f.name for f in fields(loaded)} == {f.name for f in fields(PRODUCT_R1)}


def test_make_svg_escapes_xml():
    svg = make_svg("M0 0Z", "<script>x</script>", "a&b")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "a&amp;b" in svg


def test_join_regression_core_still_green():
    for gid, expected in [("juu", 1), ("ni", 2), ("ei", 2)]:
        r = solve_glyph(all_characters()[gid], CLASSIC, k=0.15)
        assert r.after_cleanup == expected, f"{gid}: {r.after_cleanup}"
