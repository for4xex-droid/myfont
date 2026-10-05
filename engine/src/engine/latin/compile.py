"""内部用の OTF と TTF。fonts_out/build へ出す。"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import freetype
from fontmake.font_project import FontProject
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from engine.latin.build import build_glyph
from engine.latin.load import load_resolved, load_style, styles_dir
from engine.latin.outline import fit_outline
from engine.latin.ufo import FAMILY_NAMES, write_ufo

BUILD_DIR = Path(__file__).resolve().parents[4] / "fonts_out" / "build" / "latin"
PILOT = ("H", "O", "B", "V", "S", "0")


def _compile(ufo_dir: Path, dest: Path, kind: str) -> Path:
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    FontProject().run_from_ufos(
        [str(ufo_dir)],
        output=[kind],
        output_path=str(dest),
        remove_overlaps=True,
    )
    if dest.is_file():
        return dest
    found = list(dest.parent.glob(f"*.{kind}"))
    if not found:
        raise RuntimeError(f"fontmake produced no {kind} near {dest}")
    shutil.move(str(found[0]), str(dest))
    return dest


def file_stem(style_name: str) -> str:
    return FAMILY_NAMES[style_name].replace(" ", "") + "-Regular"


def build_style(style_name: str, *, glyphs: tuple[str, ...] = PILOT, out_dir: Path | None = None) -> dict[str, Path]:
    style = load_style(styles_dir() / f"{style_name}.yaml")
    records = []
    for name in glyphs:
        skeleton_name = "zero" if name == "0" else name
        resolved = load_resolved(skeleton_name, style_name)
        outline = build_glyph(resolved)
        records.append(
            (
                resolved.skeleton.glyph,
                resolved.skeleton.unicode,
                outline.advance,
                fit_outline(outline, style),
            )
        )
    root = Path(out_dir) if out_dir is not None else BUILD_DIR
    stem = file_stem(style_name)
    ufo_dir = write_ufo(style, records, root / f"{stem}.ufo")
    otf = _compile(ufo_dir, root / f"{stem}.otf", "otf")
    ttf = _compile(ufo_dir, root / f"{stem}.ttf", "ttf")
    return {"ufo": ufo_dir, "otf": otf, "ttf": ttf}


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _steps(start: tuple[float, float], end: tuple[float, float]) -> int:
    return max(8, int(math.hypot(end[0] - start[0], end[1] - start[1]) / 8.0) + 1)


def _outline_samples(path: Path, glyph: str) -> list[list[tuple[float, float]]]:
    pen = RecordingPen()
    TTFont(path).getGlyphSet()[glyph].draw(pen)
    contours: list[list[tuple[float, float]]] = []
    cur = (0.0, 0.0)
    acc: list[tuple[float, float]] = []

    def flush() -> None:
        if len(acc) >= 2:
            contours.append(list(acc))

    for op, args in pen.value:
        if op == "moveTo":
            flush()
            acc = []
            cur = (float(args[0][0]), float(args[0][1]))
            acc.append(cur)
        elif op == "lineTo":
            cur = (float(args[0][0]), float(args[0][1]))
            acc.append(cur)
        elif op == "curveTo":
            p1, p2, p3 = args
            end = (float(p3[0]), float(p3[1]))
            p0 = cur
            count = _steps(cur, end)
            for step in range(1, count + 1):
                t = step / count
                u = 1.0 - t
                acc.append(
                    (
                        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                    )
                )
            cur = end
        elif op == "qCurveTo":
            points = [None if point is None else (float(point[0]), float(point[1])) for point in args]
            if not points:
                continue
            end = acc[0] if points[-1] is None else points[-1]
            offs = [point for point in points[:-1] if point is not None]
            start = cur
            for index, off in enumerate(offs):
                nxt = end if index == len(offs) - 1 else _lerp(off, offs[index + 1], 0.5)
                count = _steps(start, nxt)
                for step in range(1, count + 1):
                    t = step / count
                    acc.append(_lerp(_lerp(start, off, t), _lerp(off, nxt, t), t))
                start = nxt
            cur = end
    flush()
    return contours


def _segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-20:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def _hausdorff(
    left: list[list[tuple[float, float]]],
    right: list[list[tuple[float, float]]],
) -> float:
    def directed(
        src: list[list[tuple[float, float]]],
        dst: list[list[tuple[float, float]]],
    ) -> float:
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for contour in dst:
            ring = contour[:-1] if contour[0] == contour[-1] else contour
            for index, start in enumerate(ring):
                segments.append((start, ring[(index + 1) % len(ring)]))
        worst = 0.0
        for contour in src:
            for point in contour:
                worst = max(worst, min(_segment_distance(point, start, end) for start, end in segments))
        return worst

    if not left or not right:
        return float("inf")
    return max(directed(left, right), directed(right, left))


def _ink(path: Path, char: str, ppem: int) -> set[tuple[int, int]]:
    face = freetype.Face(str(path))
    face.set_char_size(ppem * 64)
    face.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bitmap = face.glyph.bitmap
    left = face.glyph.bitmap_left
    top = face.glyph.bitmap_top
    raw = bitmap.buffer
    ink: set[tuple[int, int]] = set()
    for y in range(bitmap.rows):
        start = y * bitmap.pitch
        row = raw[start : start + bitmap.width]
        for x, value in enumerate(row):
            if value:
                ink.add((left + x, top - y))
    return ink


def otf_ttf_gap(otf: Path, ttf: Path, glyph: str, *, ppem: int = 2000) -> tuple[float, float]:
    """TTF 変換の差。(ラスタ IoU, 輪郭の Hausdorff)。"""
    left = _ink(otf, glyph, ppem)
    right = _ink(ttf, glyph, ppem)
    union = len(left | right)
    iou = len(left & right) / union if union else 1.0
    return iou, _hausdorff(_outline_samples(otf, glyph), _outline_samples(ttf, glyph))
