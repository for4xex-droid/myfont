"""freetype-py による EM 正規化ラスタ（ft_1024_nohint_gray_v1）。"""

from __future__ import annotations

from typing import Any

import freetype
import numpy as np
from freetype.ft_errors import FT_Exception


def load_face(path: str, em_px: int = 1024, wght: float = 400.0) -> freetype.Face:
    face = freetype.Face(path)
    try:
        info = face.get_variation_info()
        axes = getattr(info, "axes", None) or []
        if axes:
            coords = []
            for ax in axes:
                tag = ax.tag if hasattr(ax, "tag") else ax[0]
                if tag in (b"wght", "wght"):
                    coords.append(float(wght))
                else:
                    default = ax.default if hasattr(ax, "default") else ax[2]
                    coords.append(float(default))
            face.set_var_design_coords(coords)
    except (AttributeError, RuntimeError, TypeError, ValueError, FT_Exception):
        # 静的フォントや variation API 非対応は無視（掟8b: 可変は fetch でインスタンス化済み想定）
        pass
    face.set_pixel_sizes(em_px, em_px)
    return face


def render_glyph_gray(
    face: freetype.Face, char: str, *, hinting: bool = False
) -> tuple[np.ndarray, dict[str, Any]]:
    flags = freetype.FT_LOAD_RENDER
    if not hinting:
        flags |= freetype.FT_LOAD_NO_HINTING
    face.load_char(char, flags)
    glyph = face.glyph
    bitmap = glyph.bitmap
    w, h = bitmap.width, bitmap.rows
    pitch = bitmap.pitch
    buf = bytes(bitmap.buffer)
    meta: dict[str, Any] = {
        "width": w,
        "rows": h,
        "pitch": pitch,
        "left": glyph.bitmap_left,
        "top": glyph.bitmap_top,
        "advance_x": glyph.advance.x / 64.0,
        "units_per_EM": face.units_per_EM,
        "glyph_index": face.get_char_index(ord(char)),
    }
    if w == 0 or h == 0:
        return np.zeros((0, 0), dtype=np.uint8), meta
    arr = np.zeros((h, w), dtype=np.uint8)
    for row in range(h):
        start = row * pitch
        if pitch >= w:
            row_bytes = buf[start : start + w]
        else:
            row_bytes = buf[start : start + max(0, pitch)].ljust(w, b"\x00")[:w]
        arr[row, :] = np.frombuffer(row_bytes, dtype=np.uint8)
    return arr, meta


def place_on_em_canvas(gray: np.ndarray, meta: dict[str, Any], em_px: int = 1024) -> np.ndarray:
    canvas = np.zeros((em_px, em_px), dtype=np.uint8)
    h, w = gray.shape if gray.size else (0, 0)
    if h == 0 or w == 0:
        return canvas
    baseline = int(em_px * 0.88)
    x0 = (em_px - int(meta["advance_x"])) // 2 + int(meta["left"])
    y0 = baseline - int(meta["top"])
    x1, y1 = x0 + w, y0 + h
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(em_px, x1), min(em_px, y1)
    gx0, gy0 = cx0 - x0, cy0 - y0
    canvas[cy0:cy1, cx0:cx1] = gray[gy0 : gy0 + (cy1 - cy0), gx0 : gx0 + (cx1 - cx0)]
    return canvas
