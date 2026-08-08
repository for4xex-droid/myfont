"""十の縦/横コントラスト（交点回避走査）。"""

from __future__ import annotations

from typing import Any

import numpy as np


def _longest_run(binary_row: np.ndarray) -> int:
    best = cur = 0
    for v in binary_row:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def measure_juu_contrast(
    canvas: np.ndarray,
    *,
    threshold: int = 128,
    em_px: int = 1024,
    scan_fracs: tuple[float, ...] = (0.15, 0.22),
    max_run_frac: float = 0.35,
) -> dict[str, Any]:
    bin_img = canvas >= threshold
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty", "value": None}
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    face_h = y_max - y_min + 1
    face_w = x_max - x_min + 1

    vert_cands: list[int] = []
    for frac in scan_fracs:
        for sign in (-1, 1):
            yy = cy + sign * int(face_h * frac)
            if 0 <= yy < em_px:
                run = _longest_run(bin_img[yy, x_min : x_max + 1])
                if 2 <= run < face_w * max_run_frac:
                    vert_cands.append(run)

    horiz_cands: list[int] = []
    for frac in scan_fracs:
        for sign in (-1, 1):
            xx = cx + sign * int(face_w * frac)
            if 0 <= xx < em_px:
                run = _longest_run(bin_img[y_min : y_max + 1, xx])
                if 2 <= run < face_h * max_run_frac:
                    horiz_cands.append(run)

    if not vert_cands or not horiz_cands:
        return {
            "status": "low_confidence",
            "reason": "scan candidates empty",
            "value": None,
            "vert_cands": vert_cands,
            "horiz_cands": horiz_cands,
        }

    vert = float(np.median(vert_cands))
    horiz = float(np.median(horiz_cands))
    contrast = vert / horiz if horiz > 0 else None
    return {
        "status": "ok",
        "value": contrast,
        "value_secondary": horiz,
        "vert_thickness_px": vert,
        "horiz_thickness_px": horiz,
        "contrast_v_over_h": contrast,
        "vert_cands": vert_cands,
        "horiz_cands": horiz_cands,
        "reason": "ok",
    }
