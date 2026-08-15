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
