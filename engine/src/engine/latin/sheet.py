"""H O B V S 0 × 4様式の比較シート。閾値は凍結しない。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine.latin.build import GlyphOutline, build_glyph
from engine.latin.load import load_resolved

GLYPHS = ("H", "O", "B", "V", "S", "zero")
STYLES = ("modern", "classic", "chic", "pop")
_LABELS = {
    "modern": "モダン",
    "classic": "クラシック",
    "chic": "シック",
    "pop": "ポップ",
    "zero": "0",
}
_FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _paint(draw: ImageDraw.ImageDraw, outline: GlyphOutline, ox: float, baseline: float, scale: float) -> None:
    def xy(point):
        return (ox + point.x * scale, baseline - point.y * scale)

    for contour, hole in zip(outline.contours, outline.holes):
        if hole:
            continue
        draw.polygon([xy(p) for p in contour], fill=(0, 0, 0))
    for contour, hole in zip(outline.contours, outline.holes):
        if not hole:
            continue
        draw.polygon([xy(p) for p in contour], fill=(255, 255, 255))


def render_pilot_sheet(path: Path) -> Path:
    """6字×4様式を1枚の PNG にする。返り値は書き出したパス。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    outlines = {(style, glyph): build_glyph(load_resolved(glyph, style)) for style in STYLES for glyph in GLYPHS}
    scale = 0.42
    label_w = 168
    head_h = 56
    max_advance = max(item.advance for item in outlines.values())
    cell_w = int(max_advance * scale) + 36
    cell_h = int(920 * scale) + 28
    width = label_w + cell_w * len(GLYPHS)
    height = head_h + cell_h * len(STYLES)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _font(22)
    small = _font(18)
    for col, glyph in enumerate(GLYPHS):
        title = _LABELS.get(glyph, glyph)
        draw.text((label_w + col * cell_w + 16, 12), title, fill=(40, 40, 40), font=font)
    for row, style in enumerate(STYLES):
        top = head_h + row * cell_h
        draw.text((16, top + cell_h / 2 - 14), _LABELS[style], fill=(40, 40, 40), font=small)
        for col, glyph in enumerate(GLYPHS):
            outline = outlines[(style, glyph)]
            ox = label_w + col * cell_w + (cell_w - outline.advance * scale) / 2
            baseline = top + cell_h - 36
            _paint(draw, outline, ox, baseline, scale)
    image.save(path)
    return path
