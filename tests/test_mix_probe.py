"""混植捨てシートは正本 UFO を書かない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "make_mix_probe.py"
    spec = importlib.util.spec_from_file_location("make_mix_probe", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_refuse_shipping_ufo():
    mod = _load()
    with pytest.raises(ValueError, match="shipping UFO"):
        mod.assert_throwaway_dest(mod.SHIP_UFO)
    with pytest.raises(ValueError, match="shipping UFO"):
        mod.assert_throwaway_dest(mod.SHIP_UFO / "glyphs")


def test_allow_scratch(tmp_path: Path):
    mod = _load()
    dest = tmp_path / "MyMincho-mix.ufo"
    assert mod.assert_throwaway_dest(dest) == dest.resolve()


def test_mix_text_charset_is_documented():
    text = (ROOT / "proofs" / "texts" / "mix.txt").read_text(encoding="utf-8")
    assert "だ" not in text
    assert "漢" not in text
    assert "十日と二日" in text
