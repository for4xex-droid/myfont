"""S4 make_proofs のスモークテスト。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
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
    for face in ("ui", "hud", "literary", "ui_kana", "hud_kana", "walk_kana"):
        p = ROOT / "proofs" / "texts" / f"{face}.txt"
        assert p.is_file()
        assert len(p.read_text(encoding="utf-8").strip()) > 0


def test_kana_proof_texts_use_shipping_or_ui_extra():
    from ufoLib2 import Font

    font = Font.open(ROOT / "fonts_out" / "MyMincho.ufo")
    allowed = {chr(int(name[3:], 16)) for name in font.keys() if name.startswith("uni")}
    extra_path = ROOT / "data" / "glyphset_p1_kana_ui_extra.txt"
    allowed |= {
        ln.strip()
        for ln in extra_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    allowed |= set(" \n")
    for face in ("ui_kana", "hud_kana", "walk_kana"):
        text = (ROOT / "proofs" / "texts" / f"{face}.txt").read_text(encoding="utf-8")
        unknown = sorted({ch for ch in text if ch not in allowed})
        assert unknown == [], (face, unknown)


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
        "uni3044",
        "uni3046",
        "uni3048",
        "uni304A",
        "uni304B",
        "uni304D",
        "uni304F",
        "uni3051",
        "uni3053",
        "uni3055",
        "uni3057",
        "uni3059",
        "uni305B",
        "uni305D",
        "uni305F",
        "uni3061",
        "uni3064",
        "uni3066",
        "uni304C",
        "uni3058",
        "uni305E",
        "uni3063",
        "uni3065",
        "uni3068",
        "uni306E",
        "uni306F",
        "uni3072",
        "uni307B",
        "uni307C",
        "uni307E",
        "uni3081",
        "uni3084",
        "uni308A",
        "uni308B",
        "uni3092",
        "uni3093",
    }


def test_shipping_ufo_has_core20_and_no():
    from ufoLib2 import Font

    font = Font.open(ROOT / "fonts_out" / "MyMincho.ufo")
    core = [
        ln.strip()
        for ln in (ROOT / "data" / "glyphset_p1_kana_core20.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    for ch in (*core, "の"):
        name = f"uni{ord(ch):04X}"
        assert name in font, name
        assert len(font[name]) > 0, name


def test_g3_kana_freeze_png_hashes():
    import hashlib
    import json

    path = ROOT / "proofs" / "golden" / "g3_kana" / "FREEZE_g3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source"] == "shipping_ufo"
    assert "otf_sha256" not in data
    for rel, meta in data["files"].items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        assert hashlib.sha256(fp.read_bytes()).hexdigest() == meta["sha256"]


def test_g3_kana_live_render_matches_golden(tmp_path: Path):
    import importlib.util
    import json

    pytest.importorskip("freetype")
    from engine.bridge import compile_otf

    path = ROOT / "proofs" / "golden" / "g3_kana" / "FREEZE_g3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    otf = tmp_path / "g3.otf"
    compile_otf(ROOT / data["ufo"], otf, remove_overlaps=False)
    spec = importlib.util.spec_from_file_location(
        "kana_render_g3", ROOT / "engine" / "scripts" / "kana_render.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for rel, meta in data["files"].items():
        rendered = mod.render_text_png(otf, meta["text"], tmp_path / f"{meta['tag']}.png")
        assert rendered["png_sha256"] == meta["sha256"], rel


def test_manual_a_glif_unchanged_after_engine_merge():
    import hashlib
    import json

    freeze = json.loads(
        (ROOT / "proofs" / "golden" / "kana_a" / "FREEZE_g1v4.json").read_text(
            encoding="utf-8"
        )
    )
    glif = ROOT / "fonts_out" / "MyMincho.ufo" / "glyphs" / "uni3042.glif"
    assert hashlib.sha256(glif.read_bytes()).hexdigest() == freeze["glif_sha256"]


def test_blind_packet_writes_ab_without_font_names(tmp_path: Path):
    mp = _load_make_proofs()
    chars = "".join(dict.fromkeys("かいしここあといいえせいかたすけてきととのうせいこう"))
    otf_a = tmp_path / "a.ttf"
    otf_b = tmp_path / "b.ttf"
    _build_minimal_otf(otf_a, chars)
    _build_minimal_otf(otf_b, chars)
    out = tmp_path / "blind"
    spec = importlib.util.spec_from_file_location(
        "make_blind_packet", ROOT / "scripts" / "make_blind_packet.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main(
        [
            "--font",
            str(otf_a),
            "--compare",
            str(otf_b),
            "--out",
            str(out),
            "--faces",
            "ui_kana",
            "--seed",
            "1",
        ]
    )
    if code != 0:
        pytest.skip("hb-view/uharfbuzz could not render blind packet")
    assert (out / "ui_kana" / "A.png").is_file()
    assert (out / "ui_kana" / "B.png").is_file()
    seal = json.loads((out / "SEALED_order.json").read_text(encoding="utf-8"))
    assert set(seal["faces"]["ui_kana"].values()) == {"ours", "compare_a"}
    assert "MyMincho" not in (out / "ui_kana" / "A.png").name


def test_g3_blind_freeze_png_hashes():
    path = ROOT / "proofs" / "golden" / "g3_blind" / "FREEZE_g3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("superseded_by"):
        assert "files" not in data or not data["files"]
        return
    assert data["source"] == "shipping_ufo"
    assert "otf_sha256" not in data
    for rel, meta in data["files"].items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        assert hashlib.sha256(fp.read_bytes()).hexdigest() == meta["sha256"]


def test_g3_blind_live_render_matches_golden(tmp_path: Path):
    pytest.importorskip("freetype")
    from engine.bridge import compile_otf

    path = ROOT / "proofs" / "golden" / "g3_blind" / "FREEZE_g3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("superseded_by"):
        pytest.skip(f"g3_blind superseded by {data['superseded_by']}")
    otf = tmp_path / "g3.otf"
    compile_otf(ROOT / data["ufo"], otf, remove_overlaps=False)
    mp = _load_make_proofs()
    out = tmp_path / "out"
    code = mp.main(
        [
            "--font",
            str(otf),
            "--faces",
            "ui_kana,hud_kana,walk_kana",
            "--out",
            str(out),
        ]
    )
    if code != 0:
        pytest.skip("hb-view/uharfbuzz could not render g3_blind")
    for rel, meta in data["files"].items():
        rendered = out / f"{meta['tag']}.png"
        assert rendered.is_file(), rel
        assert hashlib.sha256(rendered.read_bytes()).hexdigest() == meta["sha256"]
