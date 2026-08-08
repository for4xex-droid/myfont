"""T7: 一時フォント化 bridge（union → フォント空間 → UFO → OTF）。

内部座標は COORDINATE_SPACE（現状 svg_y_down_legacy）のまま。
UFO 書き出し時のみ y_for_font() でフォント空間へ変換する（GOLDENRULES 掟1）。
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pathops import PathVerb

from engine.curve_refit import RefitConfig, load_refit_config, refit_contours
from engine.extra_skeletons import all_characters, all_labels
from engine.geometry import UPM, y_for_font
from engine.join_solver import SolveResult, solve_glyph, split_contours
from engine.params import PARAM_SETS, MinchoParams

logger = logging.getLogger(__name__)

# コア試験字（T7/T7+: 十・二・三・永。三は san_uroko 用）
CORE_GLYPHS: dict[str, dict[str, Any]] = {
    "juu": {"name": "uni5341", "unicode": 0x5341, "char": "十"},
    "ni": {"name": "uni4E8C", "unicode": 0x4E8C, "char": "二"},
    "san": {"name": "uni4E09", "unicode": 0x4E09, "char": "三"},
    "ei": {"name": "uni6C38", "unicode": 0x6C38, "char": "永"},
}


@dataclass
class BridgeGlyphResult:
    glyph_id: str
    char: str
    contours_after_cleanup: int
    font_contours: list[list[tuple[float, float]]]
    winding: dict[str, Any] = field(default_factory=dict)
    refit: dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgeBuildResult:
    params_name: str
    ufo_dir: Path
    otf_path: Path
    glyphs: list[BridgeGlyphResult]
    fill_check: dict[str, Any] = field(default_factory=dict)
    measure_juu: dict[str, Any] = field(default_factory=dict)


def extract_contours_xy(path) -> list[list[tuple[float, float]]]:
    """pathops Path → 折れ線輪郭（内部座標）。"""
    out: list[list[tuple[float, float]]] = []
    for contour in split_contours(path):
        pts: list[tuple[float, float]] = []
        for verb, p in contour:
            if verb in (PathVerb.MOVE, PathVerb.LINE):
                pts.append((float(p[0][0]), float(p[0][1])))
            elif verb == PathVerb.QUAD:
                pts.append((float(p[0][0]), float(p[0][1])))
                pts.append((float(p[1][0]), float(p[1][1])))
            elif verb == PathVerb.CUBIC:
                pts.append((float(p[0][0]), float(p[0][1])))
                pts.append((float(p[1][0]), float(p[1][1])))
                pts.append((float(p[2][0]), float(p[2][1])))
        if len(pts) >= 3:
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3:
                out.append(pts)
    return out


def shoelace(contour: Sequence[tuple[float, float]]) -> float:
    pts = list(contour)
    if len(pts) < 3:
        return 0.0
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def to_font_contours(
    contours_internal: Sequence[Sequence[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """内部座標 → フォント空間（Y上）。"""
    return [[(x, y_for_font(y)) for x, y in c] for c in contours_internal]


def ensure_positive_fill(
    contours: Sequence[Sequence[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], dict[str, Any]]:
    """
    CFF/OTF 向けに塗り輪郭を正面積（反時計）へ揃える。

    コア試験字（十/二/永）には意図的カウンターが無い前提（spike3 同）。
    口・日など穴付き字は入れ子判定が別途必要。
    """
    out: list[list[tuple[float, float]]] = []
    before = []
    reversed_flags = []
    for c in contours:
        pts = list(c)
        if pts and pts[0] == pts[-1]:
            pts = pts[:-1]
        a = shoelace(pts)
        before.append(a)
        if a < 0:
            out.append(list(reversed(pts)))
            reversed_flags.append(True)
        else:
            out.append(pts)
            reversed_flags.append(False)
    return out, {
        "areas_before": before,
        "areas_after": [shoelace(c) for c in out],
        "reversed": reversed_flags,
        "strategy": "all-positive-fill",
    }


def solve_to_font_contours(
    glyph_id: str,
    params: MinchoParams,
    *,
    k: float = 0.15,
    refit_cfg: RefitConfig | None = None,
) -> BridgeGlyphResult:
    chars = all_characters()
    if glyph_id not in chars:
        raise KeyError(f"unknown glyph id: {glyph_id}")
    labels = all_labels()
    result: SolveResult = solve_glyph(chars[glyph_id], params, k=k)
    internal = extract_contours_xy(result.path)
    cfg = refit_cfg if refit_cfg is not None else load_refit_config()
    refit_out = refit_contours(internal, cfg)
    # extract 後の輪郭数と比較（pathops 件数と抽出フィルタがずれる余地があるため）
    if len(refit_out.contours) != len(internal):
        raise ValueError(
            f"curve_refit changed contour count for {glyph_id}: "
            f"{len(internal)} -> {len(refit_out.contours)}"
        )
    font = to_font_contours(refit_out.contours)
    font, winding = ensure_positive_fill(font)
    meta = CORE_GLYPHS.get(glyph_id, {})
    return BridgeGlyphResult(
        glyph_id=glyph_id,
        char=str(meta.get("char") or labels.get(glyph_id, glyph_id)),
        contours_after_cleanup=result.after_cleanup,
        font_contours=font,
        winding=winding,
        refit=refit_out.meta,
    )


def _notdef_contours() -> list[list[tuple[float, float]]]:
    outer = [(100.0, 100.0), (900.0, 100.0), (900.0, 800.0), (100.0, 800.0)]
    inner = [(180.0, 180.0), (180.0, 720.0), (820.0, 720.0), (820.0, 180.0)]
    return [outer, inner]


def _draw_contours(glyph, contours: Sequence[Sequence[tuple[float, float]]]) -> None:
    pen = glyph.getPen()
    for contour in contours:
        if len(contour) < 3:
            continue
        pts = list(contour)
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        pen.moveTo(pts[0])
        for pt in pts[1:]:
            pen.lineTo(pt)
        pen.closePath()


def build_ufo(
    glyph_results: Sequence[BridgeGlyphResult],
    *,
    family_name: str,
    style_name: str = "Regular",
    out_dir: Path,
) -> Path:
    import ufoLib2

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    font = ufoLib2.Font()
    font.info.familyName = family_name
    font.info.styleName = style_name
    font.info.unitsPerEm = UPM
    font.info.ascender = 880
    font.info.descender = -120
    font.info.xHeight = 500
    font.info.capHeight = 800
    font.info.openTypeOS2TypoAscender = 880
    font.info.openTypeOS2TypoDescender = -120
    font.info.openTypeOS2TypoLineGap = 0
    font.info.openTypeOS2WinAscent = 880
    font.info.openTypeOS2WinDescent = 120

    nd = font.newGlyph(".notdef")
    nd.width = UPM
    _draw_contours(nd, _notdef_contours())

    for gr in glyph_results:
        meta = CORE_GLYPHS.get(gr.glyph_id)
        if meta is None:
            raise ValueError(f"glyph {gr.glyph_id} not in CORE_GLYPHS (T7 MVP)")
        g = font.newGlyph(meta["name"])
        g.width = UPM
        g.unicodes = [meta["unicode"]]
        _draw_contours(g, gr.font_contours)

    font.save(out_dir)
    return out_dir


def compile_otf(ufo_dir: Path, otf_path: Path) -> Path:
    """ufoLib2 UFO → OTF（fontmake）。"""
    from fontmake.font_project import FontProject

    otf_path = otf_path.resolve()
    otf_path.parent.mkdir(parents=True, exist_ok=True)
    if otf_path.exists():
        otf_path.unlink()

    project = FontProject()
    project.run_from_ufos(
        [str(ufo_dir)],
        output=["otf"],
        output_path=str(otf_path),
    )
    if not otf_path.is_file():
        # fontmake がディレクトリ出力する場合のフォールバック
        candidates = list(otf_path.parent.glob("*.otf"))
        if not candidates:
            raise RuntimeError(f"fontmake produced no OTF near {otf_path}")
        shutil.move(str(candidates[0]), str(otf_path))
    return otf_path


def check_fill_juu(otf_path: Path, *, em_px: int = 256) -> dict[str, Any]:
    """十のラスタ ink_ratio で塗り反転を簡易検知（spike3 同趣旨）。"""
    import freetype
    import numpy as np

    face = freetype.Face(str(otf_path))
    face.set_char_size(em_px * 64)
    juu_ch = str(CORE_GLYPHS["juu"]["char"])
    face.load_char(juu_ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bitmap = face.glyph.bitmap
    if bitmap.width == 0 or bitmap.rows == 0:
        return {"ok": False, "reason": "empty raster", "ink_ratio": 0.0}
    buf = np.array(bitmap.buffer, dtype=np.uint8).reshape(bitmap.rows, bitmap.width)
    ink_ratio = float((buf >= 128).mean())
    inverted = ink_ratio > 0.55
    return {
        "ok": (not inverted) and ink_ratio > 0.02,
        "ink_ratio": ink_ratio,
        "inverted_suspect": inverted,
        "em_px": em_px,
        "glyph_bitmap": [bitmap.width, bitmap.rows],
    }


def _try_import_fontdb_measure():
    """リポジトリ隣接の fontdb を優先 import（T7 計測の物差し統一）。"""
    import sys

    try:
        from fontdb.probes.juu_contrast import measure_juu_contrast
        from fontdb.render.freetype_raster import (
            load_face,
            place_on_em_canvas,
            render_glyph_gray,
        )

        return measure_juu_contrast, load_face, place_on_em_canvas, render_glyph_gray
    except ImportError:
        pass
    repo_fontdb = Path(__file__).resolve().parents[3] / "fontdb" / "src"
    if repo_fontdb.is_dir() and str(repo_fontdb) not in sys.path:
        sys.path.insert(0, str(repo_fontdb))
        try:
            from fontdb.probes.juu_contrast import measure_juu_contrast
            from fontdb.render.freetype_raster import (
                load_face,
                place_on_em_canvas,
                render_glyph_gray,
            )

            return measure_juu_contrast, load_face, place_on_em_canvas, render_glyph_gray
        except ImportError:
            return None
    return None


def measure_juu_from_otf(otf_path: Path, *, em_px: int = 1024, threshold: int = 128) -> dict[str, Any]:
    """OTF の十を EM キャンバスに置いてコントラスト計測（profile 想定: ft_1024_nohint_gray_v1）。"""
    import freetype
    import numpy as np

    imported = _try_import_fontdb_measure()
    if imported is not None:
        measure_juu_contrast, load_face, place_on_em_canvas, render_glyph_gray = imported
        juu_ch = str(CORE_GLYPHS["juu"]["char"])
        face = load_face(str(otf_path), em_px=em_px)
        gray, meta = render_glyph_gray(face, juu_ch, hinting=False)
        canvas = place_on_em_canvas(gray, meta, em_px=em_px)
        out = measure_juu_contrast(canvas, threshold=threshold, em_px=em_px)
        out["profile"] = "ft_1024_nohint_gray_v1"
        return out

    juu_ch = str(CORE_GLYPHS["juu"]["char"])
    face = freetype.Face(str(otf_path))
    face.set_pixel_sizes(em_px, em_px)
    face.load_char(juu_ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bitmap = face.glyph.bitmap
    if bitmap.width == 0 or bitmap.rows == 0:
        return {"status": "fail", "reason": "empty"}
    gray = np.array(bitmap.buffer, dtype=np.uint8).reshape(bitmap.rows, bitmap.width)
    canvas = np.zeros((em_px, em_px), dtype=np.uint8)
    top = max(0, (em_px - bitmap.rows) // 2)
    left = max(0, (em_px - bitmap.width) // 2)
    h = min(bitmap.rows, em_px - top)
    w = min(bitmap.width, em_px - left)
    canvas[top : top + h, left : left + w] = gray[:h, :w]
    bin_img = canvas >= threshold
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty"}
    return {
        "status": "ok",
        "ink_bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "ink_ratio": float(bin_img.mean()),
        "note": "fontdb not installed; contrast probe skipped",
    }


def build_temp_font(
    params_name: str = "classic",
    *,
    glyph_ids: Sequence[str] | None = None,
    out_root: Path | None = None,
    family_name: str | None = None,
    keep_ufo: bool = True,
) -> BridgeBuildResult:
    """コア字を接合→一時 UFO/OTF 化する T7 エントリポイント。"""
    if params_name not in PARAM_SETS:
        raise KeyError(f"unknown params: {params_name}")
    params = PARAM_SETS[params_name]
    ids = list(glyph_ids or CORE_GLYPHS.keys())
    root = Path(out_root) if out_root else Path(tempfile.mkdtemp(prefix="mymincho_t7_"))
    root.mkdir(parents=True, exist_ok=True)
    fam = family_name or f"MyMinchoT7-{params_name}"
    ufo_dir = root / f"{fam}.ufo"
    otf_path = root / f"{fam}-Regular.otf"

    glyph_results = [solve_to_font_contours(gid, params) for gid in ids]
    build_ufo(glyph_results, family_name=fam, out_dir=ufo_dir)
    compile_otf(ufo_dir, otf_path)
    fill = check_fill_juu(otf_path)
    measure = measure_juu_from_otf(otf_path)
    if not keep_ufo:
        shutil.rmtree(ufo_dir, ignore_errors=True)
    return BridgeBuildResult(
        params_name=params_name,
        ufo_dir=ufo_dir,
        otf_path=otf_path,
        glyphs=glyph_results,
        fill_check=fill,
        measure_juu=measure,
    )


def write_bridge_report(result: BridgeBuildResult, path: Path) -> Path:
    payload = {
        "params_name": result.params_name,
        "ufo_dir": str(result.ufo_dir),
        "otf_path": str(result.otf_path),
        "fill_check": result.fill_check,
        "measure_juu": result.measure_juu,
        "glyphs": [
            {
                "glyph_id": g.glyph_id,
                "char": g.char,
                "contours_after_cleanup": g.contours_after_cleanup,
                "n_font_contours": len(g.font_contours),
                "winding": g.winding,
                "refit": g.refit,
            }
            for g in result.glyphs
        ],
        "params_snapshot": asdict(PARAM_SETS[result.params_name]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
