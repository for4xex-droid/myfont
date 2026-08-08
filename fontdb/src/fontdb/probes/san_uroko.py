"""三の上横画右端うろこ相対サイズ。"""

from __future__ import annotations

from typing import Any

import numpy as np


def measure_san_uroko(
    canvas: np.ndarray,
    *,
    threshold: int = 128,
    top_region_frac: float = 0.45,
    projection_peak_frac: float = 0.45,
    fallback_top_frac: float = 0.28,
    body_column_frac: tuple[float, float] = (0.35, 0.70),
    right_roi_frac: float = 0.88,
    smooth_kernel: int = 5,
    clear_protrusion_px: float = 3.0,
    clear_relative_min: float = 0.15,
    stylistic_zero_px: float = 2.0,
    stylistic_zero_relative_max: float = 0.08,
    height_boost_px: float = 4.0,
    height_boost_relative_min: float = 0.10,
) -> dict[str, Any]:
    bin_img = canvas >= threshold
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty", "value": None}

    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    face_h = y_max - y_min + 1
    face_w = x_max - x_min + 1
    glyph = bin_img[y_min : y_max + 1, x_min : x_max + 1]

    row_proj = glyph.sum(axis=1).astype(float)
    kernel = np.ones(smooth_kernel) / float(smooth_kernel)
    smooth = np.convolve(row_proj, kernel, mode="same")
    top_cut = max(8, int(face_h * top_region_frac))
    top_region = smooth[:top_cut]
    if top_region.max() < 3:
        return {"status": "fail", "reason": "no top stroke peak", "value": None}

    peak_y = int(np.argmax(top_region))
    peak_val = float(top_region[peak_y])
    thresh_proj = peak_val * projection_peak_frac
    lo = peak_y
    while lo > 0 and smooth[lo - 1] >= thresh_proj:
        lo -= 1
    hi = peak_y
    while hi < top_cut - 1 and smooth[hi + 1] >= thresh_proj:
        hi += 1
    band_h = hi - lo + 1
    used_fallback = False
    if band_h < 4 or band_h > face_h * 0.22:
        used_fallback = True
        lo = 0
        hi = max(8, int(face_h * fallback_top_frac)) - 1

    margin = max(4, int(band_h * 0.8))
    y_lo = max(0, lo - margin)
    y_hi = min(face_h - 1, hi + max(2, band_h // 3))
    roi = glyph[y_lo : y_hi + 1, :]

    col_top: list[int] = []
    col_bot: list[int] = []
    for c in range(roi.shape[1]):
        ink = np.where(roi[:, c])[0]
        if len(ink):
            col_top.append(int(ink.min()))
            col_bot.append(int(ink.max()))
        else:
            col_top.append(-1)
            col_bot.append(-1)

    valid = [i for i, t in enumerate(col_top) if t >= 0]
    if len(valid) < max(10, int(face_w * 0.3)):
        return {
            "status": "low_confidence",
            "reason": "few ink columns in top stroke ROI",
            "value": None,
            "peak_y_rel": peak_y,
            "used_fallback_band": used_fallback,
        }

    lo_c, hi_c = body_column_frac
    mid_cols = [c for c in valid if lo_c * face_w <= c <= hi_c * face_w]
    if len(mid_cols) < 5:
        mid_cols = valid[int(len(valid) * lo_c) : int(len(valid) * hi_c)]
    if not mid_cols:
        return {"status": "low_confidence", "reason": "no mid columns", "value": None}

    body_top = float(np.median([col_top[c] for c in mid_cols]))
    body_bot = float(np.median([col_bot[c] for c in mid_cols]))
    body_thick = body_bot - body_top + 1
    if body_thick < 2:
        return {
            "status": "low_confidence",
            "reason": "body thickness < 2px",
            "value": None,
            "body_thickness_px": body_thick,
        }

    right_cols = [c for c in valid if c >= int(face_w * right_roi_frac)]
    if len(right_cols) < 3:
        right_cols = valid[int(len(valid) * right_roi_frac) :]
    if not right_cols:
        return {"status": "low_confidence", "reason": "no right columns", "value": None}

    right_top = min(col_top[c] for c in right_cols)
    protrusion_px = max(0.0, body_top - right_top)
    right_heights = [col_bot[c] - col_top[c] + 1 for c in right_cols]
    height_boost = max(0.0, float(np.max(right_heights)) - body_thick)
    relative = protrusion_px / body_thick if body_thick > 0 else 0.0

    detail = {
        "body_thickness_px": body_thick,
        "uroko_protrusion_px": protrusion_px,
        "uroko_height_boost_px": height_boost,
        "uroko_relative_to_stroke": relative,
        "peak_y_rel": peak_y,
        "band_lo_hi": [lo, hi],
        "roi_y_abs": [y_min + y_lo, y_min + y_hi],
        "used_fallback_band": used_fallback,
        "right_top_rel": right_top,
        "body_top_rel": body_top,
    }

    if protrusion_px >= clear_protrusion_px and relative >= clear_relative_min:
        status, reason = "ok", "clear uroko protrusion"
    elif protrusion_px < stylistic_zero_px and relative < stylistic_zero_relative_max:
        status, reason = "ok", "stylistic zero or negligible uroko (value≈0)"
    elif height_boost >= height_boost_px and relative >= height_boost_relative_min:
        status, reason = "ok", "accepted via height_boost"
    else:
        status, reason = (
            "low_confidence",
            f"ambiguous protrusion (px={protrusion_px:.1f}, rel={relative:.3f}, boost={height_boost:.1f})",
        )

    return {
        "status": status,
        "reason": reason,
        "value": relative,
        "value_secondary": protrusion_px,
        **detail,
    }
