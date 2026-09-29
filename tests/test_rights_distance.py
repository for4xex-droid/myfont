"""権利用レイ距離。品質合否には使わない。合成ラスタのみ（掟4）。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "rights_distance.py"
    spec = importlib.util.spec_from_file_location("rights_distance", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _disk(size: int, r: float, cy: float | None = None, cx: float | None = None) -> np.ndarray:
    yy, xx = np.ogrid[:size, :size]
    cy = (size - 1) / 2 if cy is None else cy
    cx = (size - 1) / 2 if cx is None else cx
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def _ring(size: int, r_out: float, r_in: float) -> np.ndarray:
    return _disk(size, r_out) & ~_disk(size, r_in)


def test_extractor_version_is_pinned():
    mod = _load()
    cfg = mod.load_config()
    assert cfg["extractor_version"] == "0.1.0"
    assert cfg["purpose"] == "rights_floor_only"
    assert cfg["quality_gate"] is False


def test_identical_distance_is_zero():
    mod = _load()
    a = _ring(64, 24, 14)
    assert mod.ray_distance(a, a) == 0.0


def test_translation_after_pack_is_near_zero():
    mod = _load()
    a = np.zeros((80, 80), dtype=bool)
    a[10:40, 10:40] = _disk(30, 12)
    b = np.zeros((80, 80), dtype=bool)
    b[35:65, 40:70] = _disk(30, 12)
    pa, pb = mod.pack_bbox(a, 64), mod.pack_bbox(b, 64)
    assert mod.ray_distance(pa, pb) < 0.04


def test_ray_sees_stroke_width_iou_misses():
    """bbox 正規化 IoU は太い輪と細い輪を近く見る。レイは幅ヒストで離す。"""
    mod = _load()
    thick = _ring(80, 30, 12)
    thin = _ring(80, 30, 22)
    pt, pn = mod.pack_bbox(thick, 64), mod.pack_bbox(thin, 64)
    iou = mod.iou(pt, pn)
    ray = mod.ray_distance(pt, pn)
    assert iou > 0.40
    assert ray > 0.08


def test_no_pass_fail_api():
    mod = _load()
    assert not hasattr(mod, "quality_pass")
    assert not hasattr(mod, "is_beautiful")
    a = _disk(32, 10)
    d = mod.rights_report(a, a)
    assert d["quality_gate"] is False
    assert "pass" not in d
    assert d["ray_distance"] == 0.0
    assert d["iou"] == 1.0
