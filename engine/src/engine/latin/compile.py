"""内部用の OTF と TTF。fonts_out/build へ出す。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fontmake.font_project import FontProject

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
