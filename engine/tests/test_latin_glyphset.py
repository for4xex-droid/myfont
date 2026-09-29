"""工程1: 仕様の必須集合・glyphset ファイル・AGL 名が一致し、収録外は拒否する。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLYPHSET = ROOT / "data" / "glyphset_latin_required.txt"
SPEC = ROOT / "docs" / "生成書体の仕様.md"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_three_sources_list_the_same_39_characters_in_order():
    spec = _load(ROOT / "scripts" / "generated_face_spec.py", "generated_face_spec")
    ship = _load(ROOT / "engine" / "scripts" / "ship_gate.py", "ship_gate")
    from engine.latin.glyphset import REQUIRED_CHARS

    from_spec = spec.load_spec(SPEC).required
    from_file = tuple(ship.load_glyphset(GLYPHSET))
    assert from_spec == REQUIRED_CHARS == from_file
    assert len(REQUIRED_CHARS) == 39
    assert REQUIRED_CHARS[-2:] == (" ", "\u00a0")


def test_glyph_names_roundtrip_against_fonttools():
    from fontTools.agl import UV2AGL, toUnicode

    from engine.latin.glyphset import GLYPH_NAMES, REQUIRED_CHARS, character, glyph_name

    names = tuple(UV2AGL.get(ord(ch), f"uni{ord(ch):04X}") for ch in REQUIRED_CHARS)
    assert GLYPH_NAMES == names
    assert names[-2:] == ("space", "uni00A0")
    assert len(set(names)) == 39
    for ch, name in zip(REQUIRED_CHARS, names, strict=True):
        assert toUnicode(name) == ch
        assert glyph_name(ch) == name
        assert character(name) == ch


@pytest.mark.parametrize(
    "ch",
    ["a", "\t", "\u3000", "\u2009", "あ", "\\", "Ａ", "", "0 ", ".", ","],
)
def test_character_outside_the_required_set_is_refused(ch: str):
    from engine.latin.glyphset import glyph_name, reject_outside

    with pytest.raises(ValueError):
        glyph_name(ch)
    with pytest.raises(ValueError):
        reject_outside([ch])


@pytest.mark.parametrize("name", ["zero0", "Zero", "uni0030", "nbspace", "uni0020", "fraction", ""])
def test_unknown_glyph_name_is_refused(name: str):
    from engine.latin.glyphset import character

    with pytest.raises(ValueError):
        character(name)


def test_required_set_itself_is_accepted():
    from engine.latin.glyphset import REQUIRED_CHARS, reject_outside

    reject_outside(REQUIRED_CHARS)
    reject_outside(())


def test_glyphset_file_rejects_duplicates_and_multichar_lines(tmp_path: Path):
    from engine.latin.glyphset import REQUIRED_CHARS, read_glyphset_file, reject_outside

    dup = tmp_path / "dup.txt"
    dup.write_text("A\nA\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_glyphset_file(dup)

    wide = tmp_path / "wide.txt"
    wide.write_text("AB\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_glyphset_file(wide)

    empty = tmp_path / "empty.txt"
    empty.write_text("# only\n\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_glyphset_file(empty)

    blank = tmp_path / "blank.txt"
    blank.write_bytes(b"")
    with pytest.raises(ValueError):
        read_glyphset_file(blank)

    commented = tmp_path / "commented.txt"
    commented.write_text("A\n# note\nA\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_glyphset_file(commented)

    padded = tmp_path / "padded.txt"
    padded.write_text(" A\n", encoding="utf-8")
    assert read_glyphset_file(padded) == ("A",)

    bom = tmp_path / "bom.txt"
    bom.write_bytes(b"\xef\xbb\xbfA\n")
    assert read_glyphset_file(bom) == ("A",)

    outside = tmp_path / "outside.txt"
    outside.write_text("a\n", encoding="utf-8")
    assert read_glyphset_file(outside) == ("a",)
    with pytest.raises(ValueError):
        reject_outside(read_glyphset_file(outside))

    missing = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        read_glyphset_file(missing)

    codepoints = tmp_path / "codepoints.txt"
    codepoints.write_text("A\nU+0020\nU+00A0\n", encoding="utf-8")
    assert read_glyphset_file(codepoints) == ("A", " ", "\u00a0")

    for bad in ("U+20\n", "u+0020\n", "U+00G0\n", "U+110000\n", "U+0000\n", "U+0020 A\n"):
        broken = tmp_path / "broken.txt"
        broken.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            read_glyphset_file(broken)

    dup_cp = tmp_path / "dup_cp.txt"
    dup_cp.write_text("A\nU+0041\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_glyphset_file(dup_cp)

    assert read_glyphset_file(GLYPHSET) == REQUIRED_CHARS
