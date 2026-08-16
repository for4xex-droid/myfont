"""S4 make_proofs のスモークテスト。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_make_proofs():
    path = ROOT / "scripts" / "make_proofs.py"
    spec = importlib.util.spec_from_file_location("make_proofs", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _build_minimal_otf(path: Path, chars: str) -> None:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    fb = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef"] + [f"uni{ord(c):04X}" for c in chars]
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})

    def box_glyph():
        pen = TTGlyphPen(None)
        pen.moveTo((80, 0))
        pen.lineTo((80, 700))
        pen.lineTo((720, 700))
        pen.lineTo((720, 0))
        pen.closePath()
        return pen.glyph()

    glyphs = {n: box_glyph() for n in glyph_order}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (1000, 80) for n in glyph_order})
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupNameTable(
        {
            "familyName": "ProofTest",
            "styleName": "Regular",
            "uniqueFontIdentifier": "ProofTest-Regular",
            "fullName": "ProofTest Regular",
            "psName": "ProofTest-Regular",
            "version": "Version 0.001",
        }
    )
    fb.setupPost()
    fb.save(str(path))


def test_proof_texts_exist():
    for face in ("ui", "hud", "literary"):
        p = ROOT / "proofs" / "texts" / f"{face}.txt"
        assert p.is_file()
        assert len(p.read_text(encoding="utf-8").strip()) > 0


def test_make_proofs_renders(tmp_path: Path):
    mp = _load_make_proofs()
    # Cover a few chars that appear in ui.txt
    chars = "設定開始続けるやめるはいいいえメニュー保存接続エラーレベルHP攻撃力所持金あいアイテムを使いますか？0123456789 /+G"
    # Unique
    uniq = "".join(dict.fromkeys(chars))
    otf = tmp_path / "p.ttf"
    _build_minimal_otf(otf, uniq)
    out = tmp_path / "out"
    # Only ui to keep fixture small; missing cmap chars may tofu but hb-view still writes PNG
    code = mp.main(["--font", str(otf), "--faces", "ui", "--out", str(out)])
    # May fail if many .notdef — still expect png attempt via hb-view
    png = out / "ui.png"
    if png.is_file():
        assert png.stat().st_size > 0
        assert code in (0, 1)
    else:
        pytest.skip("hb-view/uharfbuzz could not render in this environment")


def test_manual_glyphs_core20():
    text = (ROOT / "fonts_out" / "manual_glyphs.txt").read_text(encoding="utf-8")
    names = {
        ln.strip().lstrip("#").strip()
        for ln in text.splitlines()
        if "uni" in ln
    }
    drawn = {
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    }
    core = [
        ln.strip()
        for ln in (ROOT / "data" / "glyphset_p1_kana_core20.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(core) == 20
    for ch in core:
        assert f"uni{ord(ch):04X}" in names
    assert drawn == {
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
    }
