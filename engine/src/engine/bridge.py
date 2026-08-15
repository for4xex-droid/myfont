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
from engine.kana import KANA_GLYPH_META, kana_characters
from engine.params import PARAM_SETS, MinchoParams

logger = logging.getLogger(__name__)

# コア試験字（T7/T7+: 十・二・三・永。三は san_uroko 用）
CORE_GLYPHS: dict[str, dict[str, Any]] = {
    "juu": {"name": "uni5341", "unicode": 0x5341, "char": "十"},
    "ni": {"name": "uni4E8C", "unicode": 0x4E8C, "char": "二"},
    "san": {"name": "uni4E09", "unicode": 0x4E09, "char": "三"},
    "ei": {"name": "uni6C38", "unicode": 0x6C38, "char": "永"},
}

# 穴付き漢字など、extra_skeletons 由来で UFO 化するメタ（Phase 0a）
EXTRA_GLYPHS: dict[str, dict[str, Any]] = {
    "kuchi": {"name": "uni53E3", "unicode": 0x53E3, "char": "口"},
    "nichi": {"name": "uni65E5", "unicode": 0x65E5, "char": "日"},
    "ta": {"name": "uni7530", "unicode": 0x7530, "char": "田"},
    "naka": {"name": "uni4E2D", "unicode": 0x4E2D, "char": "中"},
}

# 後方互換: 明示 passthrough が必要なテスト用
_KANA_PASSTHROUGH = RefitConfig(mode="passthrough", enabled=True)


def glyph_meta(glyph_id: str) -> dict[str, Any] | None:
    """CORE + EXTRA + 仮名 YAML メタを統合参照。"""
    if glyph_id in CORE_GLYPHS:
        return CORE_GLYPHS[glyph_id]
    if glyph_id in EXTRA_GLYPHS:
        return EXTRA_GLYPHS[glyph_id]
    # kana_characters() が KANA_GLYPH_META を埋める
    if glyph_id not in KANA_GLYPH_META:
        kana_characters()
    return KANA_GLYPH_META.get(glyph_id)


def is_kana_glyph(glyph_id: str) -> bool:
    if glyph_id in CORE_GLYPHS or glyph_id in EXTRA_GLYPHS:
        return False
    if glyph_id not in KANA_GLYPH_META:
        kana_characters()
    return glyph_id in KANA_GLYPH_META


@dataclass
class BridgeGlyphResult:
    glyph_id: str
    char: str
    contours_after_cleanup: int
    font_contours: list[list[tuple[float, float]]]
    winding: dict[str, Any] = field(default_factory=dict)
    refit: dict[str, Any] = field(default_factory=dict)
    # Phase 1: cubic_fit 時の ContourPath（UFO 描画優先）
    font_paths: list[Any] | None = None


@dataclass
class BridgeBuildResult:
    params_name: str
    ufo_dir: Path
    otf_path: Path
    glyphs: list[BridgeGlyphResult]
    fill_check: dict[str, Any] = field(default_factory=dict)
    measure_juu: dict[str, Any] = field(default_factory=dict)


def extract_contours_xy(path) -> list[list[tuple[float, float]]]:
    """pathops Path → 折れ線輪郭（内部座標）。

    Phase 0c: QUAD/CUBIC を黙って頂点列に潰さない（サイレント幾何破損の防止）。
    曲線を流す経路を入れるときは verb 保持版へ置換する。
    """
    out: list[list[tuple[float, float]]] = []
    for contour in split_contours(path):
        pts: list[tuple[float, float]] = []
        for verb, p in contour:
            if verb in (PathVerb.MOVE, PathVerb.LINE):
                pts.append((float(p[0][0]), float(p[0][1])))
            elif verb == PathVerb.QUAD:
                raise ValueError(
                    "extract_contours_xy: QUAD verb not supported "
                    "(would corrupt geometry; use a curve-preserving extractor)"
                )
            elif verb == PathVerb.CUBIC:
                raise ValueError(
                    "extract_contours_xy: CUBIC verb not supported "
                    "(would corrupt geometry; use a curve-preserving extractor)"
                )
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


def _open_ring(contour: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in contour]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def _point_in_poly(x: float, y: float, poly: Sequence[tuple[float, float]]) -> bool:
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def _rep_point(poly: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """包含判定用の内点。頂点平均が外なら辺中点から内側へオフセットする。"""
    n = len(poly)
    if n == 0:
        return (0.0, 0.0)
    cx = sum(p[0] for p in poly) / n
    cy = sum(p[1] for p in poly) / n
    if _point_in_poly(cx, cy, poly):
        return (cx, cy)
    # 凹型・C字で重心が外れる場合: 符号つき面積で内側法線を決め、辺中点から探す
    area = shoelace(poly)
    sign = 1.0 if area >= 0 else -1.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        dx, dy = x2 - x1, y2 - y1
        nx, ny = -dy, dx
        length = (nx * nx + ny * ny) ** 0.5
        if length < 1e-12:
            continue
        nx, ny = (nx / length) * sign, (ny / length) * sign
        for dist in (2.0, 5.0, 10.0, 20.0, 40.0):
            px, py = mx + nx * dist, my + ny * dist
            if _point_in_poly(px, py, poly):
                return (px, py)
    # 最後の手段（深度0の単一輪郭では親探索に使われない）
    return (cx, cy)


def nesting_depths(
    contours: Sequence[Sequence[tuple[float, float]]],
) -> list[int]:
    """各輪郭の包含深度（0=外形、1=穴、2=穴の中の島…）。"""
    polys = [_open_ring(c) for c in contours]
    areas = [abs(shoelace(p)) for p in polys]
    depths: list[int] = []
    for i, poly in enumerate(polys):
        if len(poly) < 3:
            depths.append(0)
            continue
        rx, ry = _rep_point(poly)
        depth = 0
        for j, other in enumerate(polys):
            if i == j or len(other) < 3:
                continue
            # より大きい輪郭に内包されているときだけ親とみなす
            if areas[j] <= areas[i] + 1e-6:
                continue
            if _point_in_poly(rx, ry, other):
                depth += 1
        depths.append(depth)
    return depths


def normalize_fill_winding(
    contours: Sequence[Sequence[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], dict[str, Any]]:
    """
    CFF/OTF 向けに塗り向きを正規化する（Phase 0a）。

    前提: solve 側は fix_winding 済みで、内部座標（y-down）では
    外形=正面積・穴=負面積が決定的（pathops カナリアで固定）。
    Y 反転で全輪郭の向きが一様に裏返るため、全輪郭を一括 reverse して
    相対巻きを保存したままフォント空間（外形正・穴負）へ戻す。

    仕上げに包含深度と面積符号の整合を検証し、不整合は raise する
    （自動修正しない）。
    """
    opened = [_open_ring(c) for c in contours]
    before = [shoelace(c) for c in opened]
    # 一括 reverse（相対巻きを保存）
    out = [list(reversed(c)) if c else c for c in opened]
    after = [shoelace(c) for c in out]
    depths = nesting_depths(out)

    for i, (area, depth) in enumerate(zip(after, depths)):
        # 偶深度=外形（正）、奇深度=穴（負）
        expect_positive = (depth % 2) == 0
        if expect_positive and area <= 0:
            raise ValueError(
                f"winding verify failed: contour[{i}] depth={depth} "
                f"(outer) but signed_area={area:.3f} (expected >0)"
            )
        if (not expect_positive) and area >= 0:
            raise ValueError(
                f"winding verify failed: contour[{i}] depth={depth} "
                f"(hole) but signed_area={area:.3f} (expected <0)"
            )

    return out, {
        "areas_before": before,
        "areas_after": after,
        "depths": depths,
        "reversed": [True] * len(out),
        "strategy": "bulk-reverse-verify",
        "n_holes": sum(1 for d in depths if d % 2 == 1),
    }


def ensure_positive_fill(
    contours: Sequence[Sequence[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], dict[str, Any]]:
    """後方互換エイリアス。Phase 0a 以降は normalize_fill_winding を使う。"""
    return normalize_fill_winding(contours)


def normalize_fill_winding_paths(paths: Sequence[Any]) -> tuple[list[Any], dict[str, Any]]:
    """ContourPath 列の一括 reverse＋オンカーブ点での検証。"""
    from engine.curve_fit import ContourPath

    opened = [p if isinstance(p, ContourPath) else p for p in paths]
    reversed_paths = [p.reversed() for p in opened]
    font_like = [p.on_curve_points() for p in reversed_paths]
    # 検証のみ normalize_fill_winding に載せる（もう reverse 済みなので
    # 一時的に「正しい符号」を期待する検証関数を呼ぶ）
    depths = nesting_depths(font_like)
    after = [shoelace(c) for c in font_like]
    for i, (area, depth) in enumerate(zip(after, depths)):
        expect_positive = (depth % 2) == 0
        if expect_positive and area <= 0:
            raise ValueError(
                f"winding verify failed (path): contour[{i}] depth={depth} "
                f"(outer) but signed_area={area:.3f}"
            )
        if (not expect_positive) and area >= 0:
            raise ValueError(
                f"winding verify failed (path): contour[{i}] depth={depth} "
                f"(hole) but signed_area={area:.3f}"
            )
    return list(reversed_paths), {
        "areas_before": [shoelace(p.on_curve_points()) for p in opened],
        "areas_after": after,
        "depths": depths,
        "reversed": [True] * len(reversed_paths),
        "strategy": "bulk-reverse-verify-path",
        "n_holes": sum(1 for d in depths if d % 2 == 1),
    }


def normalize_fill_winding_overlay(
    contours: Sequence[Sequence[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], dict[str, Any]]:
    """重ね塗り: 全輪郭を外形として扱う。入れ子=穴にしない。"""
    opened = [_open_ring(c) for c in contours]
    before = [shoelace(c) for c in opened]
    out = [list(reversed(c)) if c else c for c in opened]
    after = [shoelace(c) for c in out]
    for i, area in enumerate(after):
        if area <= 0:
            raise ValueError(
                f"winding overlay failed: contour[{i}] signed_area={area:.3f} "
                "(expected fill >0)"
            )
    return out, {
        "areas_before": before,
        "areas_after": after,
        "depths": [0] * len(out),
        "reversed": [True] * len(out),
        "strategy": "overlay-all-fill",
        "n_holes": 0,
    }


def normalize_fill_winding_overlay_paths(
    paths: Sequence[Any],
) -> tuple[list[Any], dict[str, Any]]:
    from engine.curve_fit import ContourPath

    opened = [p if isinstance(p, ContourPath) else p for p in paths]
    reversed_paths = [p.reversed() for p in opened]
    font_like = [p.on_curve_points() for p in reversed_paths]
    after = [shoelace(c) for c in font_like]
    for i, area in enumerate(after):
        if area <= 0:
            raise ValueError(
                f"winding overlay failed (path): contour[{i}] "
                f"signed_area={area:.3f} (expected fill >0)"
            )
    return list(reversed_paths), {
        "areas_before": [shoelace(p.on_curve_points()) for p in opened],
        "areas_after": after,
        "depths": [0] * len(reversed_paths),
        "reversed": [True] * len(reversed_paths),
        "strategy": "overlay-all-fill-path",
        "n_holes": 0,
    }


def _kana_refit_config(glyph_id: str | None = None) -> RefitConfig:
    """仮名用: snapshot の kana_mode を mode に載せ替えた Config。"""
    base = load_refit_config()
    # 「あ」の十＋輪は 48 では足りない。他字のフィット選択は 48 のまま。
    anchors = 64 if glyph_id == "a" else base.cubic_max_anchors
    # overlay「あ」は穴無しでも loop 予算。combined SI は重ね塗りで偽陽性。
    a_overlay = glyph_id == "a"
    return RefitConfig(
        mode=base.kana_mode,
        epsilon_upm=base.epsilon_upm,
        max_error_upm=base.max_error_upm,
        max_points_soft=base.max_points_soft,
        min_points=base.min_points,
        enabled=base.enabled,
        kana_mode=base.kana_mode,
        cubic_max_error_upm=(
            base.cubic_loop_max_error_upm if a_overlay else base.cubic_max_error_upm
        ),
        cubic_loop_max_error_upm=base.cubic_loop_max_error_upm,
        cubic_corner_deg=base.cubic_corner_deg,
        cubic_max_anchors=anchors,
        skip_combined_self_intersect=a_overlay,
    )


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
    # 仮名單画は Stage A 延長の対象外（検出ヒットもほぼ無いが明示）
    apply_a = not is_kana_glyph(glyph_id)
    meta_pre = glyph_meta(glyph_id) or {}
    compose = str(meta_pre.get("compose") or "union")
    result: SolveResult = solve_glyph(
        chars[glyph_id],
        params,
        k=k,
        apply_stage_a=apply_a,
        compose=compose,
    )
    internal = extract_contours_xy(result.path)
    if refit_cfg is not None:
        cfg = refit_cfg
    elif is_kana_glyph(glyph_id):
        cfg = _kana_refit_config(glyph_id)
    else:
        cfg = load_refit_config()
    refit_out = refit_contours(internal, cfg)
    # extract 後の輪郭数と比較（pathops 件数と抽出フィルタがずれる余地があるため）
    if len(refit_out.contours) != len(internal):
        raise ValueError(
            f"curve_refit changed contour count for {glyph_id}: "
            f"{len(internal)} -> {len(refit_out.contours)}"
        )

    font_paths = None
    if refit_out.paths:
        # Y 反転 → winding 正規化（ContourPath）
        flipped = [
            p.transform(lambda x, y: (x, y_for_font(y))) for p in refit_out.paths
        ]
        if compose == "overlay":
            font_paths, winding = normalize_fill_winding_overlay_paths(flipped)
        else:
            font_paths, winding = normalize_fill_winding_paths(flipped)
        font = [p.on_curve_points() for p in font_paths]
    else:
        font = to_font_contours(refit_out.contours)
        if compose == "overlay":
            font, winding = normalize_fill_winding_overlay(font)
        else:
            font, winding = normalize_fill_winding(font)

    meta = glyph_meta(glyph_id) or {}
    em_fit = meta.get("em_fit")
    if em_fit is not None:
        from engine.kana.em_fit import (
            apply_em_fit_contours,
            em_fit_transform,
            path_bounds,
        )

        if font_paths:
            xf = em_fit_transform(em_fit, bounds=path_bounds(font_paths))
            font_paths = [p.transform(lambda x, y: xf(x, y)) for p in font_paths]
            font = [p.on_curve_points() for p in font_paths]
        else:
            font = apply_em_fit_contours(em_fit, font)
    return BridgeGlyphResult(
        glyph_id=glyph_id,
        char=str(meta.get("char") or labels.get(glyph_id, glyph_id)),
        contours_after_cleanup=result.after_cleanup,
        font_contours=font,
        winding=winding,
        refit=refit_out.meta,
        font_paths=font_paths,
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


def _draw_paths(glyph, paths: Sequence[Any]) -> None:
    """ContourPath 列を curveTo/lineTo で描く（Phase 1）。"""
    pen = glyph.getPen()
    for path in paths:
        pen.moveTo(path.start)
        for seg in path.segs:
            if seg[0] == "L":
                pen.lineTo((float(seg[1]), float(seg[2])))
            else:
                pen.curveTo(
                    (float(seg[1]), float(seg[2])),
                    (float(seg[3]), float(seg[4])),
                    (float(seg[5]), float(seg[6])),
                )
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
        meta = glyph_meta(gr.glyph_id)
        if meta is None:
            raise ValueError(
                f"glyph {gr.glyph_id} not in CORE/EXTRA/kana glyph meta"
            )
        g = font.newGlyph(meta["name"])
        g.width = UPM
        g.unicodes = [meta["unicode"]]
        if gr.font_paths:
            _draw_paths(g, gr.font_paths)
        else:
            _draw_contours(g, gr.font_contours)

    font.save(out_dir)
    return out_dir


def compile_otf(
    ufo_dir: Path, otf_path: Path, *, remove_overlaps: bool = True
) -> Path:
    """ufoLib2 UFO → OTF（fontmake）。

    overlay 字は重ね塗りを残すため remove_overlaps=False。
    """
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
        remove_overlaps=remove_overlaps,
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
    has_overlay = any(
        (glyph_meta(g.glyph_id) or {}).get("compose") == "overlay"
        for g in glyph_results
    )
    compile_otf(ufo_dir, otf_path, remove_overlaps=not has_overlay)
    # 十が無い仮名のみビルドでは juu 塗り検査をスキップ（fail-open にしない）
    if "juu" in ids:
        fill = check_fill_juu(otf_path)
        measure = measure_juu_from_otf(otf_path)
    else:
        fill = {"ok": True, "skipped": True, "reason": "juu not in glyph_ids"}
        measure = {"status": "skipped", "reason": "juu not in glyph_ids"}
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
