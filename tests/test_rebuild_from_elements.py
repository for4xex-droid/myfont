"""ステム＋端物テンプレ再構成。残差輪郭は使わない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "rebuild_from_elements.py"
    spec = importlib.util.spec_from_file_location("rebuild_from_elements", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_refuse_shipping_ufo():
    mod = _load()
    with pytest.raises(ValueError, match="shipping"):
        mod.assert_throwaway(ROOT / "fonts_out" / "MyMincho.ufo")


def test_juu_templates_beat_stems():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "十")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert any(s["kind"] == "h" for s in rebuilt["stems_merged"])
    assert any(s["kind"] == "v" for s in rebuilt["stems_merged"])
    h = next(s for s in rebuilt["stems_merged"] if s["kind"] == "h")
    v = next(s for s in rebuilt["stems_merged"] if s["kind"] == "v")
    assert h["x1"] - h["x0"] > 1000
    assert v["y1"] - v["y0"] > 1400
    assert rebuilt["vector_iou_templates"] > rebuilt["vector_iou_stems"]
    assert rebuilt["vector_iou_templates"] > 0.95
    assert "bar_uroko" in rebuilt["templates"]


def test_ni_uchikomi_is_triangle_not_rect():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "二")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert "junction" in rebuilt["templates"] or "uchikomi" in rebuilt["templates"]
    assert rebuilt["vector_iou_templates"] > 0.999


def test_kuchi_uses_box_uroko():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "口")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert "box_uroko" in rebuilt["templates"]
    assert rebuilt["vector_iou_templates"] > rebuilt["vector_iou_stems"]
    assert rebuilt["vector_iou_templates"] > 0.93


def test_hachi_hara_beats_stems():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "八")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert "left_hara" in rebuilt["templates"]
    assert "right_hara" in rebuilt["templates"]
    assert rebuilt["vector_iou_templates"] > rebuilt["vector_iou_stems"]
    assert rebuilt["vector_iou_templates"] > 0.97


def test_ki_spine_hara_beats_band():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "木")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.97


def test_hon_open_cross():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "本")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.97


def test_hito_sides_beat_symmetric_spine():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    from extract_ref_elements import glyph_recording, recording_to_path

    rec, _, _, _ = glyph_recording(mod.REF_DEFAULT, "人")
    exact = recording_to_path(rec)
    src = max(mod._ops_rings(exact), key=len)
    spine_paths = []
    side_paths = []
    for outer, inner in mod.split_hara_pair_chains(src):
        fitted = mod.fit_hara_spine_from_sides(outer, inner)
        spine_paths.append(mod.outline_from_spine(*fitted))
        side_paths.append(mod.outline_from_sides(outer, inner))
    spine_iou = mod.vector_iou(exact, mod.combine(spine_paths, mod.union))[0]
    side_iou = mod.vector_iou(exact, mod.combine(side_paths, mod.union))[0]
    assert side_iou > spine_iou
    assert side_iou > 0.94


def test_hito_split_pair():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "人")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.999


def test_iri_split_pair():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "入")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.999
    roof = next(s for s in rebuilt["stems_merged"] if s["kind"] == "h")
    assert roof["x1"] > 1000
    assert "roof_shoulder" in rebuilt["templates"]


def test_ei_separates_ten_and_hane():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "永")
    assert "ten" in row["roles"]
    assert "hane" in row["roles"]
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.97
    v = next(s for s in rebuilt["stems_merged"] if s["kind"] == "v")
    h = max((s for s in rebuilt["stems_merged"] if s["kind"] == "h"), key=lambda s: s["y0"])
    assert v["y1"] >= h["y0"] - 1


def test_mata_skips_roof_when_counter():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "又")
    assert row["n_counter"] >= 1
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert "roof_shoulder" not in rebuilt["templates"]
    assert rebuilt["vector_iou_templates"] > 0.95


def test_bun_pinch_keeps_unsimple_sides():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "文")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_higashi_keeps_inner_bars():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "東")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_gen_rebuilds_without_far_joins():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "言")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_furu_box_under_crossbar():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "古")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_shoku_wide_uroko_is_sides():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "食")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.97


def test_kaze_sides_beat_geom_caps():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "風")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_kuni_ink_filter_beats_hollow_stems():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "国")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_stems"] > 0.70
    assert rebuilt["vector_iou_templates"] > 0.95


def test_kuruma_does_not_fill_waist():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "車")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.99


def test_tama_keeps_other_dot():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "玉")
    assert "other" in row["roles"]
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert "other" in rebuilt["templates"]
    assert rebuilt["vector_iou_templates"] > 0.97


def test_kokoro_rebuilds_dots():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "心")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["templates"].count("other") >= 2
    assert rebuilt["vector_iou_templates"] > 0.99


def test_suke_keeps_extra_stroke():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "少")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_te_wide_top_is_hook():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "手")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    assert rebuilt["vector_iou_templates"] > 0.95


def test_spine_gate_rejects_compound_half():
    mod = _load()
    assert mod.spine_is_simple([80.0, 90.0, 70.0], 2048.0)
    assert not mod.spine_is_simple([80.0, 176.0, 70.0], 2048.0)
    assert not mod.spine_is_simple([80.0, 320.0, 70.0], 2048.0)


def test_juu_ttf_keeps_lsb(tmp_path):
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "十")
    row["_ref"] = str(mod.REF_DEFAULT)
    rebuilt = mod.rebuild_row(row)
    dest = tmp_path / "juu.ttf"
    mod.write_rebuild_ttf([rebuilt], dest)
    ref_c = mod.render_em(mod.REF_DEFAULT, "十")
    rec_c = mod.render_em(dest, "十")
    assert mod.iou(ref_c >= mod.INK, rec_c >= mod.INK) > 0.90
