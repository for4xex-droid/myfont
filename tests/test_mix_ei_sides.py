"""永 24点はらい混植シートは正本 UFO を書かない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "make_mix_ei_sides.py"
    spec = importlib.util.spec_from_file_location("make_mix_ei_sides", path)
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
    dest = tmp_path / "MyMincho-mix-ei-sides.ufo"
    assert mod.assert_throwaway_dest(dest) == dest.resolve()


def test_map_ring_fits_dest_bbox():
    mod = _load()
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)]
    mapped = mod.map_ring(ring, [0.0, 0.0, 10.0, 4.0], [100.0, 200.0, 200.0, 280.0])
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    assert min(xs) == pytest.approx(100.0)
    assert max(xs) == pytest.approx(200.0)
    assert min(ys) == pytest.approx(200.0)
    assert max(ys) == pytest.approx(280.0)


def test_ei_sides_builds_when_ref_present():
    mod = _load()
    ref = ROOT / "fontdb" / "data" / "fonts" / "ipaex_mincho-Regular.ttf"
    if not ref.is_file():
        pytest.skip("IPAex not on disk")
    contours = mod.build_ei_sides_contours()
    assert len(contours) >= 1
    assert all(len(c) >= 3 for c in contours)
