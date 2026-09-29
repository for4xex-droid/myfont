#!/usr/bin/env python3
"""権利用レイ距離。IoU と直交する幅・交差の署名。品質合否には使わない。

合成または自前ラスタだけを測る。参照アウトラインはコピーしない（掟9）。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "rights_distance.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("quality_gate") is not False:
        raise ValueError("rights_distance must set quality_gate: false")
    if raw.get("purpose") != "rights_floor_only":
        raise ValueError("purpose must be rights_floor_only")
    return raw


def pack_bbox(canvas: np.ndarray, size: int) -> np.ndarray:
    ink = np.asarray(canvas, dtype=bool)
    ys, xs = np.where(ink)
    out = np.zeros((size, size), dtype=bool)
    if len(xs) == 0:
        return out
    crop = ink[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    from PIL import Image

    im = Image.fromarray((crop.astype(np.uint8) * 255), mode="L")
    im.thumbnail((size, size), Image.Resampling.BILINEAR)
    arr = np.array(im) >= 128
    y0 = (size - arr.shape[0]) // 2
    x0 = (size - arr.shape[1]) // 2
    out[y0 : y0 + arr.shape[0], x0 : x0 + arr.shape[1]] = arr
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def _runs(line: np.ndarray) -> tuple[int, list[int], list[int]]:
    ink, gap = [], []
    crossings = 0
    if line.size == 0:
        return 0, ink, gap
    cur = bool(line[0])
    n = 1
    for v in line[1:]:
        v = bool(v)
        if v == cur:
            n += 1
            continue
        crossings += 1
        (ink if cur else gap).append(n)
        cur = v
        n = 1
    (ink if cur else gap).append(n)
    return crossings, ink, gap


def _diag_lines(binary: np.ndarray, anti: bool) -> Iterator[np.ndarray]:
    h, w = binary.shape
    # offset: x - y (or x + y)
    if anti:
        for s in range(h + w - 1):
            pts = []
            for y in range(h):
                x = s - y
                if 0 <= x < w:
                    pts.append(binary[y, x])
            if pts:
                yield np.asarray(pts, dtype=bool)
    else:
        for s in range(-(h - 1), w):
            pts = []
            for y in range(h):
                x = s + y
                if 0 <= x < w:
                    pts.append(binary[y, x])
            if pts:
                yield np.asarray(pts, dtype=bool)


def _iter_lines(binary: np.ndarray, angle: int) -> Iterator[np.ndarray]:
    if angle == 0:
        for y in range(binary.shape[0]):
            yield binary[y, :]
    elif angle == 90:
        for x in range(binary.shape[1]):
            yield binary[:, x]
    elif angle == 45:
        yield from _diag_lines(binary, anti=False)
    elif angle == 135:
        yield from _diag_lines(binary, anti=True)
    else:
        raise ValueError(f"unsupported angle {angle}")


def ray_signature(
    binary: np.ndarray,
    *,
    angles: list[int] | None = None,
    n_bins: int | None = None,
) -> np.ndarray:
    cfg = load_config()
    angles = list(cfg["angles_deg"] if angles is None else angles)
    n_bins = int(cfg["n_bins"] if n_bins is None else n_bins)
    ink = np.asarray(binary, dtype=bool)
    width = max(ink.shape[1], 1)
    parts: list[float] = []
    for angle in angles:
        crosses: list[int] = []
        ink_hist = np.zeros(n_bins, dtype=np.float64)
        gap_hist = np.zeros(n_bins, dtype=np.float64)
        for line in _iter_lines(ink, int(angle)):
            c, inks, gaps = _runs(line)
            crosses.append(c)
            for length in inks:
                ink_hist[min(n_bins - 1, int(length / width * n_bins))] += 1
            for length in gaps:
                gap_hist[min(n_bins - 1, int(length / width * n_bins))] += 1
        arr = np.asarray(crosses, dtype=np.float64)
        parts.append(float(arr.mean()) if arr.size else 0.0)
        parts.append(float(arr.std()) if arr.size else 0.0)
        ink_hist = ink_hist / (ink_hist.sum() + 1e-9)
        gap_hist = gap_hist / (gap_hist.sum() + 1e-9)
        parts.extend(ink_hist.tolist())
        parts.extend(gap_hist.tolist())
    return np.asarray(parts, dtype=np.float64)


def ray_distance(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError("ray_distance expects same-shape packed rasters")
    sa, sb = ray_signature(a), ray_signature(b)
    return float(np.mean(np.abs(sa - sb)))


def rights_report(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    cfg = load_config()
    return {
        "extractor_version": cfg["extractor_version"],
        "purpose": cfg["purpose"],
        "quality_gate": False,
        "iou": iou(a, b),
        "ray_distance": ray_distance(a, b),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rights-floor ray distance (not a quality gate)")
    ap.add_argument("--self-png", type=Path, help="own packed or raw PNG")
    ap.add_argument("--ref-png", type=Path, help="reference packed or raw PNG")
    args = ap.parse_args(argv)
    if args.self_png is None or args.ref_png is None:
        print("library only unless --self-png and --ref-png are given")
        print("quality_gate=false extractor=" + load_config()["extractor_version"])
        return 0
    from PIL import Image

    cfg = load_config()
    size = int(cfg["pack_size"])

    def _load(path: Path) -> np.ndarray:
        arr = np.array(Image.open(path).convert("L")) < 128
        return pack_bbox(arr, size)

    report = rights_report(_load(args.self_png), _load(args.ref_png))
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
