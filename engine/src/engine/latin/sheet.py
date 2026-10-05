"""H O B V S 0 × 4様式の比較シート。閾値は凍結しない。"""

from __future__ import annotations

import math
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


def _ring(contour):
    pts = list(contour)
    if len(pts) > 1 and abs(pts[0].x - pts[-1].x) < 1e-9 and abs(pts[0].y - pts[-1].y) < 1e-9:
        pts = pts[:-1]
    return pts


def _resample(pts, step: float):
    out = [pts[0]]
    carry = 0.0
    for start, end in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(end.x - start.x, end.y - start.y)
        if length < 1e-9:
            continue
        t = step - carry
        while t <= length:
            out.append(type(start)(start.x + (end.x - start.x) * t / length, start.y + (end.y - start.y) * t / length))
            t += step
        carry = length - (t - step)
    return out[:-1]


def _curvature(pts) -> list[float]:
    """度/10単位。比較テストと同じ窓。"""
    found = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[(i - 2) % n], pts[i], pts[(i + 2) % n]
        turn = math.atan2(c.y - b.y, c.x - b.x) - math.atan2(b.y - a.y, b.x - a.x)
        turn = (turn + math.pi) % (2 * math.pi) - math.pi
        found.append(math.degrees(turn) / 6.0 * 10.0)
    return found


def render_b_curvature(path: Path) -> Path:
    """クラシックとシックの B。穴の縁から、曲がりに比例した櫛を出す。

    櫛が穴の内側へ揃って出て、赤（逆向き）が無ければ、穴は凸で曲がりが段になっていない。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = ("classic", "chic")
    scale = 0.9
    cell_w = 620
    height = 780
    image = Image.new("RGB", (cell_w * len(styles), height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _font(22)
    for col, style in enumerate(styles):
        outline = build_glyph(load_resolved("B", style))
        ox = col * cell_w + 40
        baseline = height - 40
        draw.text((ox, 16), _LABELS[style], fill=(40, 40, 40), font=font)
        _paint(draw, outline, ox, baseline, scale)
        for contour, hole in zip(outline.contours, outline.holes):
            if not hole:
                continue
            pts = _resample(_ring(contour), 6.0)
            curve = _curvature(pts)
            count = len(pts)
            # 幹との継ぎ目は直角なので、櫛は碗の右側だけにする。
            left = min(point.x for point in pts)
            right = max(point.x for point in pts)
            for index, (point, kappa) in enumerate(zip(pts, curve)):
                if point.x < left + (right - left) * 0.35:
                    continue
                a, b = pts[(index - 1) % count], pts[(index + 1) % count]
                heading = math.atan2(b.y - a.y, b.x - a.x)
                # 進行方向の左。曲がりが正なら、櫛は穴の内側へ揃う。
                left_x, left_y = -math.sin(heading), math.cos(heading)
                length = kappa * 1.6 * scale
                x0, y0 = ox + point.x * scale, baseline - point.y * scale
                color = (180, 40, 40) if kappa < 0.0 else (30, 90, 160)
                draw.line((x0, y0, x0 + left_x * length, y0 - left_y * length), fill=color, width=1)
    image.save(path)
    return path
