"""参照再現ループの骨格抽出。正本は書かない。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "reproduce_ref.py"
    spec = importlib.util.spec_from_file_location("reproduce_ref", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_refuse_shipping_ufo():
    mod = _load()
    with pytest.raises(ValueError, match="shipping"):
        mod.assert_throwaway(mod.SHIP_UFO)


def test_thin_cross_keeps_a_cross():
    mod = _load()
    img = np.zeros((40, 40), dtype=bool)
    img[18:22, 6:34] = True
    img[6:34, 18:22] = True
    skel = mod.zhang_suen(img)
    ys, xs = np.where(skel)
    assert ys.max() - ys.min() >= 20
    assert xs.max() - xs.min() >= 20
    assert 15 < int(np.median(xs)) < 25
    assert 15 < int(np.median(ys)) < 25


def test_iou_identical_is_one():
    mod = _load()
    a = np.zeros((20, 20), dtype=bool)
    a[4:16, 4:16] = True
    assert mod.iou(a, a) == 1.0
    assert mod.iou(a, ~a) == 0.0


def test_exact_ipaex_juu_near_one():
    mod = _load()
    if not mod.REF_DEFAULT.is_file():
        pytest.skip("IPAex not on disk")
    rc = mod.main(["--mode", "exact", "--chars", "十"])
    assert rc == 0
    report = (mod.OUT_DEFAULT / "report.json").read_text(encoding="utf-8")
    assert '"mode": "exact"' in report
