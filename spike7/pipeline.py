"""展開 → 写像 → prototype 肉付け → SVG/PNG。"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "prototype"))
sys.path.insert(0, str(ROOT.parent / "spike2"))

from generate_mincho import make_svg, validate_svg  # noqa: E402
from params import CLASSIC, MinchoParams  # noqa: E402
from strokes import build_stroke, strokes_to_svg_paths  # noqa: E402

from kage_parser import flatten_glyph, load_dump_index  # noqa: E402
from kage_mapper import MapResult, fallback_counts, map_flattened_strokes  # noqa: E402

log = logging.getLogger("spike7.pipeline")

DUMP_DEFAULT = ROOT.parent / "spike2" / "data" / "dump_newest_only.txt"
UPM = 1000


def resolve_glyph_name(char: str, index: dict) -> Optional[str]:
    """常用字 → dump 名（uXXXX-j 優先）。"""
    name = f"u{ord(char):x}"
    if f"{name}-j" in index:
        return f"{name}-j"
    if name in index:
        return name
    return None


def expand_and_map(char: str, index: dict) -> Tuple[MapResult, dict]:
    """1字を展開＋写像。メタ情報付き。"""
    gname = resolve_glyph_name(char, index)
    meta = {
        "char": char,
        "codepoint": f"U+{ord(char):04X}",
        "glyph_name": gname,
        "expand_ok": False,
        "n_flat": 0,
        "depth": 0,
        "missing": [],
        "error": None,
    }
    if gname is None:
        meta["error"] = "not_in_dump"
        return MapResult(), meta
    try:
        flat, depth, missing = flatten_glyph(gname, index)
    except Exception as e:
        meta["error"] = f"flatten:{e}"
        return MapResult(), meta
    meta["n_flat"] = len(flat)
    meta["depth"] = depth
    meta["missing"] = missing
    meta["expand_ok"] = len(flat) > 0 and not missing
    mapped = map_flattened_strokes(flat)
    return mapped, meta


def fatten_to_paths(mapped: MapResult, params: MinchoParams = CLASSIC):
    parts = []
    for s in mapped.strokes:
        parts.extend(build_stroke(s, params))
    d = strokes_to_svg_paths(parts)
    return d, parts


def write_svg(path: Path, path_d: str, title: str) -> List[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(make_svg(path_d, title), encoding="utf-8")
    return validate_svg(str(path))


def polygons_to_png(parts: Sequence[Sequence], path: Path, size: int = 512) -> None:
    """ポリゴンを白地黒塗りで PNG 化（重ね塗り）。"""
    img = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(img)
    scale = size / UPM
    for poly in parts:
        if len(poly) < 3:
            continue
        xy = [(p.x * scale, p.y * scale) for p in poly]
        draw.polygon(xy, fill=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def render_char(
    char: str,
    index: dict,
    out_dir: Path,
    *,
    params: MinchoParams = CLASSIC,
    basename: Optional[str] = None,
) -> Dict[str, Any]:
    """1字フルパイプライン。"""
    mapped, meta = expand_and_map(char, index)
    result: Dict[str, Any] = {
        **meta,
        "n_mapped": len(mapped.strokes),
        "skipped": mapped.skipped,
        "fallbacks": fallback_counts(mapped.warnings),
        "fallback_total": len(mapped.warnings),
        "svg": None,
        "png": None,
        "svg_issues": [],
        "render_ok": False,
        "error": meta.get("error"),
    }
    if mapped.strokes:
        try:
            d, parts = fatten_to_paths(mapped, params)
            stem = basename or f"u{ord(char):04x}_{char}"
            svg_path = out_dir / f"{stem}.svg"
            png_path = out_dir / f"{stem}.png"
            issues = write_svg(svg_path, d, f"{char} / kage→prototype / {params.name}")
            polygons_to_png(parts, png_path)
            result["svg"] = str(svg_path)
            result["png"] = str(png_path)
            result["svg_issues"] = issues
            result["n_polygons"] = len(parts)
            result["render_ok"] = not issues and bool(d.strip())
        except Exception as e:
            result["error"] = f"render:{e}"
            result["traceback"] = traceback.format_exc()
            log.exception("render failed for %s", char)
    elif not result["error"]:
        result["error"] = "no_strokes_after_map"
    return result


def load_index(dump: Path = DUMP_DEFAULT):
    log.info("loading dump %s", dump)
    return load_dump_index(dump)
