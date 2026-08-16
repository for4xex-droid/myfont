"""kana_fit_step 用の帯照合（ゲート非接続）。"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    assert width_keys_ok([fat_entry], entry_max=22.0) is True
    assert width_keys_ok([thin], hw_max=19.0) is False


def test_em_fit_sets_lsb_and_preserves_aspect():
    from engine.kana.em_fit import apply_em_fit_contours, font_bounds
    from engine.kana.schema import EmFitSpec

    box = [(200.0, 200.0), (700.0, 200.0), (700.0, 700.0), (200.0, 700.0)]
    out = apply_em_fit_contours(EmFitSpec(scale=1.5, target_lsb=100.0), [box])
    xmin, ymin, xmax, ymax = font_bounds(out)
    assert xmin == pytest.approx(100.0)
    assert xmax - xmin == pytest.approx(750.0)
    assert (xmax - xmin) / (ymax - ymin) == pytest.approx(1.0)


def test_em_fit_fail_closed_on_empty_and_y_overflow():
    from engine.kana.em_fit import apply_em_fit_contours, font_bounds
    from engine.kana.schema import EmFitSpec

    with pytest.raises(ValueError, match="empty"):
        font_bounds([])
    with pytest.raises(ValueError, match="empty"):
        apply_em_fit_contours(EmFitSpec(scale=1.0, target_lsb=10.0), [])
    box = [(200.0, 200.0), (700.0, 200.0), (700.0, 700.0), (200.0, 700.0)]
    with pytest.raises(ValueError, match="leaves 0"):
        apply_em_fit_contours(EmFitSpec(scale=10.0, target_lsb=10.0), [box])


def test_em_fit_uses_control_point_bounds():
    """on-curve だけ見ると LSB が過大になる。ハンドルを bbox に入れる。"""
    from engine.curve_fit import ContourPath
    from engine.kana.em_fit import em_fit_transform, path_bounds
    from engine.kana.schema import EmFitSpec

    path = ContourPath(
        start=(200.0, 200.0),
        segs=[
            ("C", 50.0, 300.0, 400.0, 300.0, 400.0, 200.0),
            ("L", 400.0, 400.0),
            ("L", 200.0, 400.0),
            ("L", 200.0, 200.0),
        ],
    )
    xf = em_fit_transform(EmFitSpec(scale=1.0, target_lsb=100.0), bounds=path_bounds([path]))
    assert xf(50.0, 300.0)[0] == pytest.approx(100.0)


def test_current_kana_freeze_png_hashes():
    """現行 FREEZE_g*.json の PNG / 骨格 YAML SHA がディスクと一致（superseded は除外）。"""
    import hashlib
    import json
    from pathlib import Path

    from engine.kana import load_kana_skeleton, skeletons_dir

    repo = Path(__file__).resolve().parents[2]
    freezes = sorted((repo / "proofs" / "golden").glob("kana_*/FREEZE_*.json"))
    assert freezes, "expected kana freeze manifests"
    checked = 0
    for path in freezes:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("superseded_by"):
            assert "files" not in data or not data["files"]
            continue
        files = data.get("files") or {}
        assert files, path
        for rel, meta in files.items():
            fp = (repo / rel).resolve()
            assert fp.is_relative_to(repo.resolve()), rel
            assert fp.is_file(), rel
            digest = hashlib.sha256(fp.read_bytes()).hexdigest()
            assert digest == meta["sha256"], f"{path.name} {rel}"
            checked += 1
        gid = path.parent.name.removeprefix("kana_")
        if data.get("source") == "manual_ufo":
            if data.get("glif"):
                glif = (repo / data["glif"]).resolve()
            else:
                glyph = data.get("glyph", f"uni{ord('あ'):04X}")
                glif = (repo / data["ufo"] / "glyphs" / f"{glyph}.glif").resolve()
            assert glif.is_relative_to(repo.resolve()), data.get("glif")
            assert glif.is_file(), glif
            assert hashlib.sha256(glif.read_bytes()).hexdigest() == data["glif_sha256"]
            assert "otf_sha256" not in data, (
                f"{path.name}: shared-UFO OTF hash is not a per-glyph freeze"
            )
            continue
        yaml_path = skeletons_dir() / f"{gid}.yaml"
        assert yaml_path.is_file(), yaml_path
        yaml_sha = data.get("skeleton_yaml_sha256")
        assert yaml_sha, f"{path.name} missing skeleton_yaml_sha256"
        assert hashlib.sha256(yaml_path.read_bytes()).hexdigest() == yaml_sha
        if data.get("em_fit"):
            _gid, _strokes, meta = load_kana_skeleton(yaml_path)
            fit = meta.get("em_fit")
            assert fit is not None, gid
            assert fit.scale == data["em_fit"]["scale"]
            assert fit.target_lsb == data["em_fit"]["target_lsb"]
    assert checked >= 2


def test_current_kana_live_render_matches_golden(tmp_path: Path):
    """現行 FREEZE_g* をエンジン経由で再描画して SHA 照合。あは出荷 hmtx の L/R も見る。"""
    import importlib.util
    import json

    pytest.importorskip("pathops")
    pytest.importorskip("freetype")

    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    from engine.bridge import build_temp_font
    from engine.geometry import UPM

    repo = Path(__file__).resolve().parents[2]
    render_path = repo / "engine" / "scripts" / "kana_render.py"
    spec = importlib.util.spec_from_file_location("kana_render_frozen", render_path)
    assert spec is not None and spec.loader is not None
    render_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_mod)
    render_text_png = render_mod.render_text_png

    freezes = sorted((repo / "proofs" / "golden").glob("kana_*/FREEZE_*.json"))
    saw = 0
    compiled_manual: dict[str, Path] = {}
    for path in freezes:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("superseded_by"):
            continue
        gid = path.parent.name.removeprefix("kana_")
        if data.get("source") == "manual_ufo":
            from engine.bridge import compile_otf

            ufo_rel = data["ufo"]
            ufo_dir = (repo / ufo_rel).resolve()
            assert ufo_dir.is_relative_to(repo.resolve()), ufo_rel
            otf_path = compiled_manual.get(ufo_rel)
            if otf_path is None:
                otf_path = tmp_path / "manual_ufo" / Path(ufo_rel).name / "manual.otf"
                compile_otf(ufo_dir, otf_path, remove_overlaps=False)
                compiled_manual[ufo_rel] = otf_path
        else:
            result = build_temp_font(
                "product_r1",
                glyph_ids=[gid],
                out_root=tmp_path / gid,
                keep_ufo=False,
            )
            otf_path = result.otf_path
        assert otf_path.is_file(), gid
        for rel, meta in (data.get("files") or {}).items():
            text = meta["text"]
            rendered = render_text_png(
                otf_path, text, tmp_path / gid / f"{meta['tag']}.png"
            )
            assert rendered["png_sha256"] == meta["sha256"], rel
            saw += 1
        if data.get("source") == "manual_ufo":
            tt = TTFont(str(otf_path))
            single = next(
                (
                    m["text"]
                    for m in (data.get("files") or {}).values()
                    if m.get("tag") == "single"
                ),
                None,
            )
            ch = single[0] if single else "あ"
            name = tt.getBestCmap()[ord(ch)]
            aw, lsb = tt["hmtx"][name]
            gs = tt.getGlyphSet()
            bp = BoundsPen(gs)
            gs[name].draw(bp)
            xmin, _ymin, xmax, _ymax = bp.bounds
            rsb = aw - (xmax - xmin) - lsb
            scale = UPM / tt["head"].unitsPerEm
            assert 106.0 <= lsb * scale <= 146.0, (gid, ch, lsb * scale)
            assert 98.0 <= rsb * scale <= 138.0, (gid, ch, rsb * scale)
    assert saw >= 4
