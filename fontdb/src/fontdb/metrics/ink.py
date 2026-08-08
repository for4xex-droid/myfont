"""浅い glyph 指標（字面率・黒み密度・重心）。"""

from __future__ import annotations

from typing import Any

import numpy as np


def ink_metrics(canvas: np.ndarray, *, threshold: int = 128, em_px: int = 1024) -> dict[str, Any]:
    bin_img = canvas >= threshold
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "missing" if canvas.max() == 0 else "fail", "reason": "empty"}
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    area = bw * bh
    ink = int(bin_img[y0 : y1 + 1, x0 : x1 + 1].sum())
    cy_i, cx_i = np.mean(ys), np.mean(xs)
    return {
        "status": "ok",
        "ink_bbox": [x0, y0, x1, y1],
        "face_ratio": area / (em_px * em_px),
        "black_density": ink / area if area else None,
        "centroid_x_em": float(cx_i) / em_px,
        "centroid_y_em": float(cy_i) / em_px,
        "ink_pixels": ink,
    }
