"""内部用の OTF と TTF。fonts_out/build へ出す。"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from fontmake.font_project import FontProject
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from pathops import Path as SkiaPath
from pathops import PathOp
from pathops import op as path_op

from engine.curve_fit import ContourPath
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


def build_style(
    style_name: str, *, glyphs: tuple[str, ...] = PILOT, out_dir: Path | None = None
) -> dict[str, Path]:
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


def _lerp(
    a: tuple[float, float], b: tuple[float, float], t: float
) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _steps(
    start: tuple[float, float], end: tuple[float, float], spacing: float = 8.0
) -> int:
    return max(8, int(math.hypot(end[0] - start[0], end[1] - start[1]) / spacing) + 1)


def _outline_samples(
    path: Path, glyph: str, *, spacing: float = 8.0
) -> list[list[tuple[float, float]]]:
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
            count = _steps(cur, end, spacing)
            for step in range(1, count + 1):
                t = step / count
                u = 1.0 - t
                acc.append(
                    (
                        u**3 * p0[0]
                        + 3 * u * u * t * p1[0]
                        + 3 * u * t * t * p2[0]
                        + t**3 * p3[0],
                        u**3 * p0[1]
                        + 3 * u * u * t * p1[1]
                        + 3 * u * t * t * p2[1]
                        + t**3 * p3[1],
                    )
                )
            cur = end
        elif op == "qCurveTo":
            points = [
                None if point is None else (float(point[0]), float(point[1]))
                for point in args
            ]
            if not points:
                continue
            end = acc[0] if points[-1] is None else points[-1]
            offs = [point for point in points[:-1] if point is not None]
            start = cur
            for index, off in enumerate(offs):
                nxt = (
                    end if index == len(offs) - 1 else _lerp(off, offs[index + 1], 0.5)
                )
                count = _steps(start, nxt, spacing)
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
    t = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2),
    )
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
                worst = max(
                    worst,
                    min(
                        _segment_distance(point, start, end) for start, end in segments
                    ),
                )
        return worst

    if not left or not right:
        return float("inf")
    return max(directed(left, right), directed(right, left))


def _skia_design(paths: tuple[ContourPath, ...]) -> SkiaPath:
    skia = SkiaPath()
    for path in paths:
        skia.moveTo(*path.start)
        for seg in path.segs:
            if seg[0] == "L":
                skia.lineTo(float(seg[1]), float(seg[2]))
            else:
                skia.cubicTo(*(float(value) for value in seg[1:7]))
        skia.close()
    return skia


def _skia_font(font: Path, glyph: str) -> SkiaPath:
    pen = RecordingPen()
    TTFont(font).getGlyphSet()[glyph].draw(pen)
    skia = SkiaPath()
    start = (0.0, 0.0)
    for name, args in pen.value:
        if name == "moveTo":
            start = (float(args[0][0]), float(args[0][1]))
            skia.moveTo(*start)
        elif name == "lineTo":
            skia.lineTo(float(args[0][0]), float(args[0][1]))
        elif name == "curveTo":
            skia.cubicTo(*(float(value) for point in args for value in point))
        elif name == "qCurveTo":
            end = (
                start if args[-1] is None else (float(args[-1][0]), float(args[-1][1]))
            )
            offs = [
                (float(point[0]), float(point[1]))
                for point in args[:-1]
                if point is not None
            ]
            for index, off in enumerate(offs):
                nxt = (
                    end if index == len(offs) - 1 else _lerp(off, offs[index + 1], 0.5)
                )
                skia.quadTo(off[0], off[1], nxt[0], nxt[1])
        elif name == "closePath":
            skia.close()
    return skia


def _design_samples(
    paths: tuple[ContourPath, ...], per_seg: int = 24
) -> list[list[tuple[float, float]]]:
    return [path.sample(n_per_seg=per_seg) for path in paths]


def _perimeter(contours: list[list[tuple[float, float]]]) -> float:
    total = 0.0
    for contour in contours:
        for start, end in zip(contour, contour[1:] + contour[:1], strict=True):
            total += math.hypot(end[0] - start[0], end[1] - start[1])
    return total


def outline_gap(
    design: tuple[ContourPath, ...], font: Path, glyph: str
) -> tuple[float, float]:
    """設計の輪郭から書き出した輪郭までのずれ（UPM）。(最大, 平均)。平均は差の面積を周で割る。"""
    designed = _design_samples(design)
    worst = _hausdorff(designed, _outline_samples(font, glyph))
    perimeter = _perimeter(designed)
    if perimeter <= 0.0:
        return worst, float("inf")
    xor = path_op(_skia_design(design), _skia_font(font, glyph), PathOp.XOR)
    return worst, abs(xor.area) / perimeter


def _crossings(
    origin: tuple[float, float],
    direction: tuple[float, float],
    contours: list[list[tuple[float, float]]],
) -> list[float]:
    found: list[float] = []
    for contour in contours:
        ring = contour[:-1] if contour[0] == contour[-1] else contour
        for start, end in zip(ring, ring[1:] + ring[:1], strict=True):
            ex, ey = end[0] - start[0], end[1] - start[1]
            den = direction[0] * ey - direction[1] * ex
            if abs(den) < 1e-12:
                continue
            wx, wy = start[0] - origin[0], start[1] - origin[1]
            along = (wx * ey - wy * ex) / den
            where = (wx * direction[1] - wy * direction[0]) / den
            if 0.0 <= where < 1.0:
                found.append(along)
    return sorted(found)


def _thickness(
    origin: tuple[float, float],
    inward: tuple[float, float],
    contours: list[list[tuple[float, float]]],
) -> float | None:
    found = _crossings(origin, inward, contours)
    if len(found) < 2:
        return None
    near = min(range(len(found)), key=lambda index: abs(found[index]))
    if near + 1 >= len(found):
        return None
    return found[near + 1] - found[near]


def thin_change(
    design: tuple[ContourPath, ...], font: Path, glyph: str, *, limit: float
) -> float:
    """設計で limit より細い所の太さが、書き出しでどれだけ変わるか（比の最大）。

    外形は反時計回り、穴は時計回りなので、進行方向の左が墨の内側になる。
    点の間隔が 8 UPM だと、細い所で 1% 近い測り違いが出るので細かく取る。
    """
    designed = _design_samples(design, per_seg=96)
    shipped = _outline_samples(font, glyph, spacing=2.0)
    worst = 0.0
    for contour in designed:
        ring = contour[:-1] if contour[0] == contour[-1] else contour
        count = len(ring)
        for index in range(count):
            before, after = ring[index - 1], ring[(index + 1) % count]
            tx, ty = after[0] - before[0], after[1] - before[1]
            length = math.hypot(tx, ty)
            if length < 1e-9:
                continue
            inward = (-ty / length, tx / length)
            thick = _thickness(ring[index], inward, designed)
            if thick is None or not 0.5 < thick <= limit:
                continue
            other = _thickness(ring[index], inward, shipped)
            if other is None:
                return float("inf")
            worst = max(worst, abs(other / thick - 1.0))
    return worst
