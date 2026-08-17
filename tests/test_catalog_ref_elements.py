"""多面要素カタログ。輪郭点は持たない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_box_counters_and_bar_uroko_family():
    ext = _load("extract_ref_elements")
    if not ext.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    kuchi = ext.extract_char(ext.REF_DEFAULT, "口")
    hi = ext.extract_char(ext.REF_DEFAULT, "日")
    ta = ext.extract_char(ext.REF_DEFAULT, "田")
    juu = ext.extract_char(ext.REF_DEFAULT, "十")
    assert kuchi["n_counter"] == 1
    assert hi["n_counter"] == 2
    assert ta["n_counter"] == 4
    assert "bar_uroko" in juu["roles"]
    fits = [t["uroko"] for t in juu["terminals"] if t.get("uroko")]
    assert fits
    assert 4.5 < fits[0]["width_over_h"] < 6.0
    assert 3.4 < fits[0]["height_over_h"] < 4.5


def test_catalog_library_has_two_uroko_families():
    cat = _load("catalog_ref_elements")
    if not cat.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    raw = [cat.extract_char(cat.REF_DEFAULT, ch) for ch in "十二三口日"]
    lib = cat.library_from(raw)
    assert lib["bar_uroko"]["n"] >= 3
    assert lib["box_uroko"]["n"] >= 1
    assert 2.3 < lib["contrast_v_over_h"]["median"] < 2.7
    slim = cat.slim_row(raw[0])
    assert "stems" not in slim
    assert all("bounds" not in t for t in slim.get("uroko", []))
