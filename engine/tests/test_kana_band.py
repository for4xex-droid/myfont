"""kana_fit_step 用の帯照合（ゲート非接続）。"""

from __future__ import annotations

from engine.geometry import Vec2
from engine.kana.band import (
    band_violations,
    fit_step_exit,
    interpret_band_ok,
    parse_band_range,
    parse_ours_line,
    width_keys_ok,
)
from engine.strokes import SkeletonStroke, StrokeKind


def test_parse_band_range():
    assert parse_band_range("1.065 .. 1.142") == (1.065, 1.142)
    assert parse_band_range(" 0.24..0.268 ") == (0.24, 0.268)
    assert parse_band_range("nope") is None
    assert parse_band_range("3 .. 1") == (1.0, 3.0)


def test_band_violations_none_when_missing():
    assert band_violations(None, {"a": "1 .. 2"}) is None
    assert band_violations({"a": 1.5}, None) is None
    assert band_violations({"a": 1.5}, {}) is None


def test_band_violations_in_and_out():
    ours = {
        "aspect_w_over_h": 1.115,
        "ink_density": 0.24,
        "centroid_y_frac": 0.50,
    }
    band = {
        "aspect_w_over_h": "1.065 .. 1.142",
        "ink_density": "0.24 .. 0.268",
        "centroid_y_frac": "0.479 .. 0.486",
    }
    assert band_violations(ours, band) == ["centroid_y_frac"]
    ours["centroid_y_frac"] = 0.484
    assert band_violations(ours, band) == []


def test_band_violations_no_overlap_is_not_empty_ok():
    """キー名が噛み合わない／帯が読めない → [] ではなく None。"""
    ours = {"aspect_w_over_h": 1.1}
    assert band_violations(ours, {"nope": "1 .. 2"}) is None
    assert band_violations(ours, {"aspect_w_over_h": "garbage"}) is None
    assert interpret_band_ok(ours, {"nope": "1 .. 2"}, None) is False


def test_interpret_band_ok_unmeasured():
    assert interpret_band_ok(None, None, None) is None
    assert interpret_band_ok({"a": 1}, None, None) is None


def test_band_violations_bad_numeric_is_violation():
    ours = {"ink_density": "nan-ish"}
    band = {"ink_density": "0.24 .. 0.268"}
    assert band_violations(ours, band) == ["ink_density"]
    assert band_violations({"ink_density": float("nan")}, band) == ["ink_density"]


def test_parse_ours_line():
    row = parse_ours_line("OURS         1.115   0.227   0.820   0.589   0.484   0.240")
    assert row is not None
    assert row["aspect_w_over_h"] == 1.115
    assert row["ink_density"] == 0.24
    assert parse_ours_line("OURS 1 2 3") is None
    assert parse_ours_line("OURS a 0.2 0.8 0.5 0.4 0.2") is None
    assert parse_ours_line("OURSELF 1 2 3 4 5 6") is None
    assert parse_ours_line("OURS 1 2 3 4 5 nan") is None


def test_fit_step_exit_measure_fail_is_not_success():
    ok = dict(
        gate_ok=True,
        width_ok=True,
        band_ok=True,
        ref_exit=0,
        otf_present=True,
        ours_present=True,
        band_present=True,
    )
    assert fit_step_exit(**ok) == 0
    assert fit_step_exit(**{**ok, "otf_present": False, "band_ok": None, "ref_exit": None}) == 2
    assert fit_step_exit(**{**ok, "ref_exit": 2}) == 2
    assert fit_step_exit(**{**ok, "ours_present": False, "band_ok": None}) == 2
    assert fit_step_exit(**{**ok, "band_present": False, "band_ok": None}) == 2
    assert fit_step_exit(**{**ok, "gate_ok": False}) == 1
    assert fit_step_exit(**{**ok, "band_ok": False}) == 1
    assert fit_step_exit(**{**ok, "band_ok": None}) == 1


def test_width_keys_ok_per_element_entry():
    thin = SkeletonStroke(
        kind=StrokeKind.KANA_CURVE,
        points=[Vec2(0, 0), Vec2(1, 0), Vec2(2, 0), Vec2(3, 0)],
        width_keys=[(0.0, 10.0), (1.0, 20.0)],
        element_id="a",
    )
    fat_entry = SkeletonStroke(
        kind=StrokeKind.KANA_CURVE,
        points=[Vec2(0, 0), Vec2(1, 0), Vec2(2, 0), Vec2(3, 0)],
        width_keys=[(0.0, 22.0), (1.0, 10.0)],
        element_id="b",
    )
    assert width_keys_ok([thin]) is True
    # 連結先頭が細くても、後続 element の入口が太いなら不可
    assert width_keys_ok([thin, fat_entry]) is False
