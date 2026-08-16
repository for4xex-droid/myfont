"""方式A「あ」足場: 空 uni3042・背景はラスタ・マージで上書きしない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_manual_ufo_has_three_drawn_fills():
    ufo = ROOT / "fonts_out" / "MyMincho.ufo"
    assert ufo.is_dir()
    glif = (ufo / "glyphs" / "uni3042.glif").read_text(encoding="utf-8")
    assert glif.count("<contour>") == 3
    assert "<point" in glif
    assert "com.mymincho.manual" in glif


def test_manual_ufo_has_drawn_ki_sa_ta_chi():
    ufo = ROOT / "fonts_out" / "MyMincho.ufo" / "glyphs"
    expected = {
        "uni3046.glif": 2,
        "uni3048.glif": 2,
        "uni304A_.glif": 3,
        "uni304B_.glif": 3,
        "uni304D_.glif": 3,
        "uni3051.glif": 3,
        "uni3053.glif": 2,
        "uni3055.glif": 2,
        "uni3059.glif": 2,
        "uni305B_.glif": 3,
        "uni305D_.glif": 1,
        "uni305F_.glif": 4,
        "uni3061.glif": 2,
        "uni3066.glif": 1,
    }
    for name, n in expected.items():
        glif = (ufo / name).read_text(encoding="utf-8")
        assert glif.count("<contour>") == n, name
        assert "<point" in glif
        assert "com.mymincho.manual" in glif


def test_manual_drawn_fills_are_positive_area():
    """重ね塗りの交差が穴にならないこと（あで白抜けした境界）。"""
    from ufoLib2 import Font

    from engine.bridge import shoelace

    font = Font.open(ROOT / "fonts_out" / "MyMincho.ufo")
    for name in (
        "uni3042",
        "uni3046",
        "uni3048",
        "uni304A",
        "uni304B",
        "uni304D",
        "uni3051",
        "uni3053",
        "uni3055",
        "uni3059",
        "uni305B",
        "uni305D",
        "uni305F",
        "uni3061",
        "uni3066",
    ):
        glyph = font[name]
        assert len(glyph) > 0, name
        for i, contour in enumerate(glyph):
            pts = [(pt.x, pt.y) for pt in contour]
            assert shoelace(pts) > 0, f"{name} contour {i}"


def test_guide_pngs_are_raster_only():
    bg = ROOT / "proofs" / "review" / "a" / "glyphs_bg"
    for name in (
        "a_guide_ipaex.png",
        "a_guide_source_han.png",
        "a_guide_shippori.png",
        "a_guide_zen_old.png",
        "a_guide_average.png",
    ):
        p = bg / name
        assert p.is_file(), name
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_merge_skips_manual_a(tmp_path: Path):
    from ufoLib2 import Font

    dest = Font()
    g = dest.newGlyph("uni3042")
    g.width = 1000
    g.lib["com.mymincho.manual"] = True
    dest_dir = tmp_path / "dest.ufo"
    dest.save(dest_dir)

    eng = Font()
    eg = eng.newGlyph("uni3042")
    eg.width = 1000
    pen = eg.getPen()
    pen.moveTo((100, 100))
    pen.lineTo((200, 100))
    pen.lineTo((200, 200))
    pen.closePath()
    shi = eng.newGlyph("uni3057")
    shi.width = 1000
    pen = shi.getPen()
    pen.moveTo((10, 10))
    pen.lineTo((20, 10))
    pen.lineTo((20, 20))
    pen.closePath()
    eng_dir = tmp_path / "eng.ufo"
    eng.save(eng_dir)

    manual = tmp_path / "m.txt"
    manual.write_text("uni3042\n", encoding="utf-8")
    mod = _load("merge_engine_ufo")
    assert (
        mod.main(
            ["--engine", str(eng_dir), "--dest", str(dest_dir), "--manual", str(manual)]
        )
        == 0
    )
    out = Font.open(dest_dir)
    assert len(out["uni3042"]) == 0
    assert "uni3057" in out
    assert len(out["uni3057"]) == 1


def test_docs_do_not_bare_fontmake_shipping_ufo():
    forbidden = "fontmake -u fonts_out/MyMincho.ufo"
    for rel in ("fonts_out/README.md", "WORKFLOW.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert forbidden not in text, rel


def test_engine_workflow_regens_then_merges():
    text = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")
    assert "engine/scripts/regen.py" in text
    assert "merge_engine_ufo.py" in text
    assert "compile_manual_otf.py" in text
    assert "check_manual_overwrite.py --ufo fonts_out/MyMincho.ufo" in text
    assert "make_proofs.py --otf" not in text
    assert "make_proofs.py --font" in text
    assert "python scripts/density_report.py" not in text
    assert "python engine/generate.py" not in text
    assert "--glyphs juu,ei" not in text
    assert "--glyphs juu ei" in text
    assert "tests/test_join_regression.py" not in text
    assert "engine/tests/test_regression_join.py" in text
    assert "merge_manual_kana.py" in text


def test_compile_manual_otf_keeps_overlaps(tmp_path: Path, monkeypatch):
    import engine.bridge as bridge

    seen: dict[str, bool] = {}

    def fake(ufo, otf, *, remove_overlaps=True):
        seen["remove_overlaps"] = remove_overlaps
        Path(otf).parent.mkdir(parents=True, exist_ok=True)
        Path(otf).write_bytes(b"otf")
        return Path(otf)

    monkeypatch.setattr(bridge, "compile_otf", fake)
    ufo = tmp_path / "in.ufo"
    ufo.mkdir()
    otf = tmp_path / "out.otf"
    mod = _load("compile_manual_otf")
    assert mod.main(["--ufo", str(ufo), "--otf", str(otf)]) == 0
    assert seen["remove_overlaps"] is False


def test_compile_manual_otf_missing_ufo(tmp_path: Path):
    mod = _load("compile_manual_otf")
    assert mod.main(["--ufo", str(tmp_path / "nope.ufo")]) == 2


def test_compile_manual_otf_refuses_otf_inside_ufo(tmp_path: Path):
    ufo = tmp_path / "in.ufo"
    ufo.mkdir()
    mod = _load("compile_manual_otf")
    assert mod.main(["--ufo", str(ufo), "--otf", str(ufo / "nested.otf")]) == 2


def test_compile_manual_otf_compile_error(tmp_path: Path, monkeypatch):
    import engine.bridge as bridge

    def boom(ufo, otf, *, remove_overlaps=True):
        raise TypeError("fontmake failed")

    monkeypatch.setattr(bridge, "compile_otf", boom)
    ufo = tmp_path / "in.ufo"
    ufo.mkdir()
    mod = _load("compile_manual_otf")
    assert mod.main(["--ufo", str(ufo), "--otf", str(tmp_path / "out.otf")]) == 1


def test_merge_manual_kana_skips_drawn_dest(tmp_path: Path):
    from ufoLib2 import Font

    dest = Font()
    g = dest.newGlyph("uni3055")
    g.width = 1000
    pen = g.getPen()
    pen.moveTo((1, 1))
    pen.lineTo((2, 1))
    pen.lineTo((2, 2))
    pen.closePath()
    dest_dir = tmp_path / "dest.ufo"
    dest.save(dest_dir)

    src = Font()
    sg = src.newGlyph("uni3055")
    sg.width = 1000
    pen = sg.getPen()
    pen.moveTo((10, 10))
    pen.lineTo((20, 10))
    pen.lineTo((20, 20))
    pen.closePath()
    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    src.save(src_root / "さ.ufo")

    mod = _load("merge_manual_kana")
    assert (
        mod.main(["さ", "--dest", str(dest_dir), "--src-root", str(src_root)]) == 0
    )
    out = Font.open(dest_dir)
    pts = [(p.x, p.y) for p in out["uni3055"][0]]
    assert (1, 1) in pts


def test_merge_manual_kana_copies_empty_dest(tmp_path: Path):
    from ufoLib2 import Font

    dest_dir = tmp_path / "dest.ufo"
    Font().save(dest_dir)
    src = Font()
    sg = src.newGlyph("uni3055")
    sg.width = 1000
    pen = sg.getPen()
    pen.moveTo((10, 10))
    pen.lineTo((20, 10))
    pen.lineTo((20, 20))
    pen.closePath()
    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    src.save(src_root / "さ.ufo")

    mod = _load("merge_manual_kana")
    assert (
        mod.main(["さ", "--dest", str(dest_dir), "--src-root", str(src_root)]) == 0
    )
    out = Font.open(dest_dir)
    assert len(out["uni3055"]) == 1
    assert out["uni3055"].lib.get("com.mymincho.manual") is True


def test_merge_manual_kana_refuses_engine_canonical():
    mod = _load("merge_manual_kana")
    assert mod.main(["し"]) == 2
    assert mod.main(["の"]) == 2


def test_merge_manual_kana_refuses_empty_source(tmp_path: Path):
    from ufoLib2 import Font

    dest_dir = tmp_path / "dest.ufo"
    Font().save(dest_dir)
    src_root = tmp_path / "manual_kana"
    src_root.mkdir()
    Font().save(src_root / "さ.ufo")
    mod = _load("merge_manual_kana")
    assert (
        mod.main(["さ", "--dest", str(dest_dir), "--src-root", str(src_root)]) == 2
    )


def test_prepare_refuses_wipe_when_drawn(tmp_path: Path, monkeypatch):
    from ufoLib2 import Font

    ufo_dir = tmp_path / "MyMincho.ufo"
    font = Font()
    g = font.newGlyph("uni3042")
    g.width = 1000
    pen = g.getPen()
    pen.moveTo((1, 1))
    pen.lineTo((2, 1))
    pen.lineTo((2, 2))
    pen.closePath()
    font.save(ufo_dir)

    mod = _load("prepare_manual_a")
    monkeypatch.setattr(mod, "UFO_DIR", ufo_dir)
    monkeypatch.setattr(mod, "BG_DIR", tmp_path / "bg")
    assert mod.main([]) == 1
