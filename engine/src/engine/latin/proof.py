"""組見本。書き出した OTF と TTF を、ピクセルサイズで描く。黄金にはしない。"""

from __future__ import annotations

from pathlib import Path

import freetype
from PIL import Image, ImageDraw

from engine.latin.sheet import TEXT_LINES, _font

_LABELS = {
    "modern": "モダン",
    "classic": "クラシック",
    "chic": "シック",
    "pop": "ポップ",
}


def _mask(bitmap) -> Image.Image:
    pitch = bitmap.pitch
    raw = bytes(bitmap.buffer)
    width = bitmap.width
    rows = bytearray()
    step = abs(pitch)
    for y in range(bitmap.rows):
        start = y * step
        rows.extend(raw[start : start + width])
    return Image.frombytes("L", (width, bitmap.rows), bytes(rows))


def render_line(font: Path, text: str, ppem: int) -> Image.Image:
    """1行。字はフォントの送り幅で置く。"""
    face = freetype.Face(str(font))
    face.set_char_size(ppem * 64)
    upm = face.units_per_EM
    height = max(1, int((face.ascender - face.descender) / upm * ppem) + 2)
    baseline = int(face.ascender / upm * ppem)
    placed: list[tuple[int, int, Image.Image]] = []
    x = 0.0
    min_x = 0
    max_x = 1
    for char in text:
        face.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        glyph = face.glyph
        bitmap = glyph.bitmap
        left = round(x) + glyph.bitmap_left
        top = baseline - glyph.bitmap_top
        if bitmap.width and bitmap.rows:
            placed.append((left, top, _mask(bitmap)))
            min_x = min(min_x, left)
            max_x = max(max_x, left + bitmap.width)
        x += glyph.advance.x / 64.0
    max_x = max(max_x, int(x) + 1)
    shift = -min(0, min_x)
    image = Image.new("RGB", (max_x + shift + 2, height), (255, 255, 255))
    for left, top, mask in placed:
        black = Image.new("RGB", mask.size, (0, 0, 0))
        image.paste(black, (left + shift, max(0, top)), mask)
    return image


def render_contact(fonts: dict[str, Path], sizes: tuple[int, ...]) -> Image.Image:
    """様式 × 管理文字列 × ピクセルサイズを1枚に積む。"""
    label = _font(18)
    rows: list[tuple[str, Image.Image]] = []
    for ppem in sizes:
        for style, path in fonts.items():
            for text in TEXT_LINES:
                rows.append(
                    (
                        f"{_LABELS[style]} {text}  {ppem}px",
                        render_line(path, text, ppem),
                    )
                )
    label_w = 220
    width = label_w + max(image.width for _title, image in rows)
    height = sum(max(28, image.height) for _title, image in rows)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw_y = 0
    draw = ImageDraw.Draw(sheet)
    for title, image in rows:
        sheet.paste(image, (label_w, draw_y))
        draw.text((8, draw_y + 4), title, fill=(40, 40, 40), font=label)
        draw_y += max(28, image.height)
    return sheet
