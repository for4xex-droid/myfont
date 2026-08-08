"""合成キャンバスでの probe 単体テスト。"""

from __future__ import annotations

import numpy as np

from fontdb.probes.juu_contrast import measure_juu_contrast
from fontdb.probes.san_uroko import measure_san_uroko


def _plus_canvas(em: int = 256) -> np.ndarray:
    """太い縦・細い横の十（コントラスト ≈ 2）。"""
    c = np.zeros((em, em), dtype=np.uint8)
    # vertical bar thickness 40
    c[40:216, 108:148] = 255
    # horizontal bar thickness 20
    c[118:138, 40:216] = 255
    return c


def _san_canvas(em: int = 256) -> np.ndarray:
    """3本の横画。上画右端にうろこ突出。"""
    c = np.zeros((em, em), dtype=np.uint8)
    # top stroke thickness 12, with uroko protrusion upward on right
    c[50:62, 40:200] = 255
    c[40:50, 185:205] = 255  # uroko
    c[110:122, 40:210] = 255
    c[170:182, 40:220] = 255
    return c


def test_juu_contrast_roughly_two():
    res = measure_juu_contrast(_plus_canvas(), em_px=256, threshold=128)
    assert res["status"] == "ok"
    assert res["value"] is not None
    assert 1.5 < res["value"] < 3.0


def test_san_uroko_detects_protrusion():
    res = measure_san_uroko(_san_canvas(), threshold=128)
    assert res["status"] == "ok"
    assert res["value"] is not None
    assert res["value"] >= 0.15
