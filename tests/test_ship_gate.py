"""S1 ship_gate のユニットテスト（最小 OTF をその場で構築）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "scripts"))

ship_gate = pytest.importorskip("ship_gate")


def _build_minimal_otf(path: Path, chars: str = "あいう") -> None:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    fb = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef"] + [f"uni{ord(c):04X}" for c in chars]
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})

    def box_glyph():
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((700, 700))
        pen.lineTo((700, 0))
        pen.closePath()
        return pen.glyph()

    glyphs = {".notdef": box_glyph()}
    for c in chars:
        glyphs[f"uni{ord(c):04X}"] = box_glyph()
    fb.setupGlyf(glyphs)
    metrics = {n: (1000, 100) for n in glyph_order}
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupOS2(
        sTypoAscender=880,
        sTypoDescender=-120,
        usWinAscent=880,
        usWinDescent=120,
    )
    fb.setupNameTable(
        {
            "familyName": "MyMinchoTest",
            "styleName": "Regular",
            "uniqueFontIdentifier": "MyMinchoTest-Regular",
            "fullName": "MyMinchoTest Regular",
            "psName": "MyMinchoTest-Regular",
            "version": "Version 0.001",
            "copyright": "Test fixture",
        }
    )
    fb.setupPost()
    fb.save(str(path))


def test_load_glyphset_alpha():
    path = ROOT / "data" / "glyphset_alpha.txt"
    chars = ship_gate.load_glyphset(path)
    assert len(chars) >= 300
    assert "あ" in chars


def test_ship_gate_passes_minimal(tmp_path: Path):
    otf = tmp_path / "min.ttf"
    _build_minimal_otf(otf, "あいう")
    gs = tmp_path / "gs.txt"
    gs.write_text("あ\nい\nう\n", encoding="utf-8")
    results = ship_gate.run_gate(otf, gs)
    by_name = {r["name"]: r for r in results}
    assert by_name["cmap_coverage"]["ok"]
    assert by_name["notdef"]["ok"]
    assert by_name["vertical_metrics"]["ok"]
    assert by_name["name_table"]["ok"]
    assert by_name["no_hangul_cmap"]["ok"]
    assert by_name["outline_sample"]["ok"]


def test_ship_gate_detects_missing_cmap(tmp_path: Path):
    otf = tmp_path / "min.ttf"
    _build_minimal_otf(otf, "あい")
    gs = tmp_path / "gs.txt"
    gs.write_text("あ\nい\nう\n", encoding="utf-8")
    results = ship_gate.run_gate(otf, gs)
    cmap = next(r for r in results if r["name"] == "cmap_coverage")
    assert not cmap["ok"]
    assert cmap["missing_count"] == 1


def test_ship_gate_cli_requires_glyphset(tmp_path: Path):
    otf = tmp_path / "min.ttf"
    _build_minimal_otf(otf, "あ")
    # --glyphset 無しは argparse が拒否（SystemExit 2）
    with pytest.raises(SystemExit) as ei:
        ship_gate.main([str(otf)])
    assert ei.value.code == 2


def test_cmap_notdef_counts_as_missing(tmp_path: Path):
    """cmap に載っていても .notdef を指す字は欠字。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    otf = tmp_path / "nd.ttf"
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "uni3042"])
    # い (3044) をわざと .notdef にマップ
    fb.setupCharacterMap({0x3042: "uni3042", 0x3044: ".notdef"})

    def box_glyph():
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((700, 700))
        pen.lineTo((700, 0))
        pen.closePath()
        return pen.glyph()

    glyphs = {".notdef": box_glyph(), "uni3042": box_glyph()}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (1000, 100) for n in glyphs})
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupNameTable(
        {
            "familyName": "N",
            "styleName": "Regular",
            "uniqueFontIdentifier": "N",
            "fullName": "N",
            "psName": "N",
            "version": "0.1",
            "copyright": "c",
        }
    )
    fb.setupPost()
    fb.save(str(otf))
    gs = tmp_path / "gs.txt"
    gs.write_text("あ\nい\n", encoding="utf-8")
    results = ship_gate.run_gate(otf, gs)
    cmap = next(r for r in results if r["name"] == "cmap_coverage")
    assert not cmap["ok"]
    assert "い" in cmap["missing_sample"]


def test_frozen_joyo_count():
    chars = ship_gate.load_glyphset(ROOT / "data" / "glyphset_joyo2136.txt")
    assert len(chars) == 2136
    kyoiku = ship_gate.load_glyphset(ROOT / "data" / "glyphset_kyoiku1026.txt")
    assert len(kyoiku) == 1026
    assert set(kyoiku).issubset(set(chars))


def test_empty_glyphset_rejected(tmp_path: Path):
    gs = tmp_path / "empty.txt"
    gs.write_text("# comment only\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        ship_gate.load_glyphset(gs)


def test_multichar_glyphset_line_rejected(tmp_path: Path):
    gs = tmp_path / "bad.txt"
    gs.write_text("あい\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 1 character"):
        ship_gate.load_glyphset(gs)


def test_cli_empty_glyphset_exits_2(tmp_path: Path):
    otf = tmp_path / "min.ttf"
    _build_minimal_otf(otf, "あ")
    gs = tmp_path / "empty.txt"
    gs.write_text("# none\n", encoding="utf-8")
    code = ship_gate.main([str(otf), "--glyphset", str(gs)])
    assert code == 2


def test_units_per_em_checked(tmp_path: Path):
    from fontTools.ttLib import TTFont

    otf = tmp_path / "min.ttf"
    _build_minimal_otf(otf, "あ")
    tt = TTFont(str(otf))
    tt["head"].unitsPerEm = 2048
    tt.save(str(otf))
    gs = tmp_path / "gs.txt"
    gs.write_text("あ\n", encoding="utf-8")
    results = ship_gate.run_gate(otf, gs)
    metrics = next(r for r in results if r["name"] == "vertical_metrics")
    assert not metrics["ok"]
    assert any("unitsPerEm" in x for x in metrics["issues"])
