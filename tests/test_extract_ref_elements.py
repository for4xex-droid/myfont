"""exact 輪郭のステム／端物分割。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "extract_ref_elements.py"
    spec = importlib.util.spec_from_file_location("extract_ref_elements", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_ipaex_juu_split_is_lossless():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "十")
    assert row["lossless"]
    assert any(s["kind"] == "h" for s in row["stems"])
    assert any(s["kind"] == "v" for s in row["stems"])
    assert row["contrast_v_over_h"] is not None
    assert 2.0 < row["contrast_v_over_h"] < 3.0
    assert row["h_thickness_em"] is not None
    assert "bar_uroko" in row["roles"]


def test_gen_keeps_middle_bars():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "言")
    hs = [s for s in row["stems"] if s["kind"] == "h"]
    assert len(hs) >= 5
    assert all(s["thickness"] < 80 for s in hs)


def test_kuni_drops_hollow_slabs():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    row = mod.extract_char(mod.REF_DEFAULT, "国")
    assert all(s["thickness"] < 160 for s in row["stems"])
    assert any(s["kind"] == "h" and s["length"] > 1000 for s in row["stems"])
    assert any(s["kind"] == "v" for s in row["stems"])
