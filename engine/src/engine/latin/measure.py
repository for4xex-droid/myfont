"""OTF を freetype で測る。分離閾値は凍結しない。"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import freetype


def _raster(face: freetype.Face, char: str, ppem: int) -> tuple[list[bytearray], int]:
    face.set_char_size(ppem * 64)
    face.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bitmap = face.glyph.bitmap
    width = bitmap.width
    rows: list[bytearray] = []
    raw = bitmap.buffer
    for y in range(bitmap.rows):
        start = y * bitmap.pitch
        rows.append(bytearray(raw[start : start + width]))
    return rows, face.glyph.bitmap_top


def _runs(row: bytearray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    x = 0
    while x < len(row):
        if row[x] == 0:
            x += 1
            continue
        start = x
        while x < len(row) and row[x] != 0:
            x += 1
        runs.append((start, x - start))
    return runs


def _row_at(rows: list[bytearray], top: int, font_y: float, ppem: int) -> bytearray | None:
    # 1 em = 1000。ラスタの1行は 1000/ppem ユニット。
    py = top - round(font_y * ppem / 1000.0)
    if py < 0 or py >= len(rows):
        return None
    return rows[py]


def measure_otf(path: Path, *, ppem: int = 500) -> dict[str, float | str]:
    """H のステム、O のコントラスト、セリフの出、足元の丸み。単位は em 比。"""
    face = freetype.Face(str(path))
    scale = 1000.0 / ppem
    h_rows, h_top = _raster(face, "H", ppem)
    stem_samples: list[float] = []
    for y in (150, 250, 520, 620):
        row = _row_at(h_rows, h_top, y, ppem)
        if row is None:
            continue
        runs = _runs(row)
        if runs:
            stem_samples.append(runs[0][1] * scale)
    stem = statistics.median(stem_samples) if stem_samples else 0.0
    foot_width = stem
    for row in reversed(h_rows):
        runs = _runs(row)
        if runs:
            foot_width = runs[0][1] * scale
            break
    serif = max(0.0, (foot_width - stem) / 2.0) / 700.0
    taper = max(0.0, 1.0 - foot_width / stem) if stem else 0.0

    o_rows, _o_top = _raster(face, "O", ppem)
    ink_cols = [x for row in o_rows for x, value in enumerate(row) if value]
    ink_rows = [i for i, row in enumerate(o_rows) if any(row)]
    o_width = (max(ink_cols) - min(ink_cols) + 1) * scale if ink_cols else 0.0
    o_height = (max(ink_rows) - min(ink_rows) + 1) * scale if ink_rows else 0.0
    walls = _ring_walls(o_rows)
    thick = max(walls.values()) if walls else 0.0
    thin_values = [v for v in walls.values() if v > 0.0]
    thin = min(thin_values) if thin_values else 0.0
    contrast = thick / thin if thin else 0.0
    thick_deg = max(walls, key=walls.get) if walls else 0
    return {
        "stem_over_cap": stem / 700.0,
        "o_width_over_height": o_width / o_height if o_height else 0.0,
        "contrast": contrast,
        "thick_ray_deg": thick_deg,
        "serif_over_cap": serif,
        "foot_taper": taper,
    }


def _ring_walls(rows: list[bytearray]) -> dict[int, float]:
    """中心から 15 度刻みで、O の壁の厚さ（ピクセル）を測る。"""
    if not rows or not rows[0]:
        return {}
    xs = [x for row in rows for x, value in enumerate(row) if value]
    ys = [y for y, row in enumerate(rows) if any(row)]
    if not xs or not ys:
        return {}
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    width = len(rows[0])
    height = len(rows)
    walls: dict[int, float] = {}
    for deg in range(0, 180, 15):
        angle = math.radians(deg)
        dx, dy = math.cos(angle), math.sin(angle)
        walls[deg] = _wall(rows, cx, cy, dx, dy, width, height) + _wall(
            rows, cx, cy, -dx, -dy, width, height
        )
    return walls


def _wall(
    rows: list[bytearray],
    cx: float,
    cy: float,
    dx: float,
    dy: float,
    width: int,
    height: int,
) -> float:
    t = 1.0
    while True:
        x = round(cx + dx * t)
        y = round(cy + dy * t)
        if x < 0 or y < 0 or x >= width or y >= height:
            return 0.0
        if rows[y][x]:
            break
        t += 1.0
    start = t
    while True:
        x = round(cx + dx * t)
        y = round(cy + dy * t)
        if x < 0 or y < 0 or x >= width or y >= height or not rows[y][x]:
            break
        t += 1.0
    return t - start
