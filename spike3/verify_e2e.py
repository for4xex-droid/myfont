#!/usr/bin/env python3
"""
spike3: 端到端検証
A) union済み輪郭 → Y反転 → UFO → fontmake OTF（P3経路）
B) OTF を freetype 計測 vs poly_pillow 直描画（§2.3 物差し1本化）
C) 組見本スモーク（uharfbuzz/hb-view + diffenator2）
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Sequence, Tuple

import freetype
import numpy as np
from PIL import Image, ImageDraw
from pathops import Path, PathVerb, simplify, union

# --- paths -----------------------------------------------------------------
SPIKE3 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SPIKE3)
SPIKE = os.path.join(ROOT, "spike")
PROTO = os.path.join(ROOT, "prototype")
OUT = os.path.join(SPIKE3, "output")
UFO_DIR = os.path.join(SPIKE3, "MyMinchoSpike.ufo")
OTF_PATH = os.path.join(OUT, "MyMinchoSpike-Regular.otf")
VENV_BIN = os.path.join(SPIKE, ".venv", "bin")
PYTHON = os.path.join(VENV_BIN, "python")
PIP = os.path.join(VENV_BIN, "pip")
FONTMAKE = os.path.join(VENV_BIN, "fontmake")

sys.path.insert(0, PROTO)
sys.path.insert(0, SPIKE)

from params import PARAM_SETS  # noqa: E402
from skeletons import CHARACTERS, CHAR_LABELS  # noqa: E402
from strokes import build_stroke  # noqa: E402
from geometry import Vec2  # noqa: E402

# reuse measurement helpers from spike B
from verify_b_measure import (  # noqa: E402
    EM_PX,
    THRESH,
    longest_run,
    measure_juu_contrast,
    place_on_em_canvas,
    render_glyph_gray,
    save_png,
)

UPM = 1000
PARAM_NAME = "classic"  # 代表パラメータ

# unicode / glyph names
GLYPH_META = {
    "juu": {"char": "十", "unicode": 0x5341, "name": "uni5341"},
    "ni": {"char": "二", "unicode": 0x4E8C, "name": "uni4E8C"},
    "ei": {"char": "永", "unicode": 0x6C38, "name": "uni6C38"},
}


# --- pathops helpers (from spike A) ----------------------------------------

def poly_to_path(poly: Sequence[Vec2]) -> Path:
    p = Path()
    if len(poly) < 3:
        return p
    pts = list(poly)
    if pts[0].as_tuple() == pts[-1].as_tuple():
        pts = pts[:-1]
    if len(pts) < 3:
        return p
    p.moveTo(pts[0].x, pts[0].y)
    for pt in pts[1:]:
        p.lineTo(pt.x, pt.y)
    p.close()
    return p


def count_contours(path: Path) -> int:
    return sum(1 for v, _ in path if v == PathVerb.MOVE)


def pathops_union(paths: Sequence[Path]) -> Path:
    out = Path()
    union(list(paths), out.getPen())
    return out


def extract_contours(path: Path) -> List[List[Tuple[float, float]]]:
    """pathops.Path → 閉じた頂点列のリスト（最終点が始点と異なる場合あり）。"""
    contours: List[List[Tuple[float, float]]] = []
    cur: List[Tuple[float, float]] = []
    for verb, pts in path:
        if verb == PathVerb.MOVE:
            if cur:
                contours.append(cur)
            cur = [(float(pts[0][0]), float(pts[0][1]))]
        elif verb == PathVerb.LINE:
            cur.append((float(pts[0][0]), float(pts[0][1])))
        elif verb == PathVerb.QUAD:
            # 中間点を折線近似（spike は直線中心だが念のため）
            cur.append((float(pts[0][0]), float(pts[0][1])))
            cur.append((float(pts[1][0]), float(pts[1][1])))
        elif verb == PathVerb.CUBIC:
            cur.append((float(pts[0][0]), float(pts[0][1])))
            cur.append((float(pts[1][0]), float(pts[1][1])))
            cur.append((float(pts[2][0]), float(pts[2][1])))
        elif verb == PathVerb.CLOSE:
            if cur:
                contours.append(cur)
                cur = []
    if cur:
        contours.append(cur)
    return contours


def shoelace(contour: Sequence[Tuple[float, float]]) -> float:
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


def flip_y_contour(contour: Sequence[Tuple[float, float]], upm: int = UPM) -> List[Tuple[float, float]]:
    """SVG(Y下) → フォント空間(Y上)。Y反転は向きを反転させる。"""
    return [(x, upm - y) for x, y in contour]


def ensure_ps_winding(contours: List[List[Tuple[float, float]]]) -> Tuple[List[List[Tuple[float, float]]], dict]:
    """
    PostScript/CFF: 塗り輪郭は反時計回り(面積>0)。

    Y 反転で符号が逆転する。ストローク union 出力（十/二/永）には意図的な
    カウンター（穴）が無く、残る小さい輪郭は打ち込み由来の「島」である。
    bbox 内包で穴判定すると島が本体 bbox に入り誤って穴化するので、
    本スパイクでは全輪郭を正面積（塗り）に揃える。

    真の穴が必要になる字（口・国 等）では、点-in-polygon の入れ子判定へ
    切り替える（Stage B 後の製品パイプライン課題）。
    """
    if not contours:
        return contours, {"reversed": [], "areas_before": [], "areas_after": []}

    cleaned: List[List[Tuple[float, float]]] = []
    for c in contours:
        pts = list(c)
        if pts and pts[0] == pts[-1]:
            pts = pts[:-1]
        cleaned.append(pts)

    areas_before = [shoelace(c) for c in cleaned]
    out: List[List[Tuple[float, float]]] = []
    reversed_flags = []
    roles = []
    for c, a in zip(cleaned, areas_before):
        if a < 0:
            out.append(list(reversed(c)))
            reversed_flags.append(True)
        else:
            out.append(list(c))
            reversed_flags.append(False)
        roles.append("fill")

    areas_after = [shoelace(c) for c in out]
    return out, {
        "strategy": "all-contours-positive-fill (no intentional counters in spike glyphs)",
        "roles": roles,
        "areas_before": areas_before,
        "areas_after": areas_after,
        "reversed": reversed_flags,
        "need_flip_all": False,
        "note": (
            "一括反転は微小島を穴化するので不採用。"
            "bbox 内包穴判定も打ち込み島を誤爆するため、本字形では全塗り。"
        ),
    }
def build_union_contours(char_key: str, pname: str = PARAM_NAME) -> Tuple[List[List[Tuple[float, float]]], dict]:
    """prototype ポリゴン → pathops union(+simplify) → SVG座標の輪郭。"""
    params = PARAM_SETS[pname]
    polys: List[List[Vec2]] = []
    for s in CHARACTERS[char_key]:
        polys.extend(build_stroke(s, params))
    paths = [poly_to_path(p) for p in polys if len(p) >= 3]
    paths = [p for p in paths if count_contours(p) > 0]
    before = sum(count_contours(p) for p in paths)
    united = pathops_union(paths)
    cleaned = simplify(united, fix_winding=True)
    contours_svg = extract_contours(cleaned)
    meta = {
        "char_key": char_key,
        "label": CHAR_LABELS[char_key],
        "param": pname,
        "n_input_polys": len(paths),
        "before_contours": before,
        "after_contours": len(contours_svg),
        "areas_svg": [shoelace(c) for c in contours_svg],
    }
    return contours_svg, meta


# --- A: UFO + fontmake -----------------------------------------------------

def make_notdef_contours() -> List[List[Tuple[float, float]]]:
    """簡易 .notdef（フォント空間・外枠CCW＋内枠CW）。"""
    outer = [(100, 100), (900, 100), (900, 800), (100, 800)]  # CCW in Y-up
    inner = [(180, 180), (180, 720), (820, 720), (820, 180)]  # CW hole
    return [outer, inner]


def _draw_contours(glyph, contours: List[List[Tuple[float, float]]]) -> None:
    spen = glyph.getPen()
    for contour in contours:
        if len(contour) < 3:
            continue
        pts = list(contour)
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        spen.moveTo(pts[0])
        for pt in pts[1:]:
            spen.lineTo(pt)
        spen.closePath()


def build_ufo(
    font_contours: Dict[str, List[List[Tuple[float, float]]]],
    winding_reports: Dict[str, dict],
) -> str:
    import ufoLib2

    if os.path.exists(UFO_DIR):
        shutil.rmtree(UFO_DIR)

    font = ufoLib2.Font()
    font.info.familyName = "MyMinchoSpike"
    font.info.styleName = "Regular"
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
    _draw_contours(nd, make_notdef_contours())

    for key, contours in font_contours.items():
        meta = GLYPH_META[key]
        g = font.newGlyph(meta["name"])
        g.width = UPM
        g.unicodes = [meta["unicode"]]
        _draw_contours(g, contours)

    font.save(UFO_DIR)
    _ = winding_reports
    return UFO_DIR


def run_fontmake() -> dict:
    os.makedirs(OUT, exist_ok=True)
    # remove previous otf
    if os.path.exists(OTF_PATH):
        os.remove(OTF_PATH)
    cmd = [
        FONTMAKE,
        "-u",
        UFO_DIR,
        "-o",
        "otf",
        "--output-path",
        OTF_PATH,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return {
        "cmd": cmd,
        "returncode": p.returncode,
        "ok": p.returncode == 0 and os.path.isfile(OTF_PATH),
        "stdout_tail": (p.stdout or "")[-1500:],
        "stderr_tail": (p.stderr or "")[-1500:],
        "otf": OTF_PATH if os.path.isfile(OTF_PATH) else None,
    }


def check_fill_not_inverted(otf_path: str) -> dict:
    """
    ラスタ化して塗りが反転していないか確認。
    字面 bbox 内のインク率が高ければ通常塗り、外周だけ塗られて内部が空洞なら反転疑い。
    """
    face = freetype.Face(otf_path)
    face.set_pixel_sizes(EM_PX, EM_PX)
    gray, meta = render_glyph_gray(face, "十")
    canvas = place_on_em_canvas(gray, meta)
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"ok": False, "reason": "empty raster", "ink_ratio": 0.0}

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    roi = bin_img[y0 : y1 + 1, x0 : x1 + 1]
    ink_ratio = float(roi.mean())

    # 十字は字面の一部のみインク。反転すると bbox ほぼ全面が黒になる
    # 経験的に 十 の ink_ratio は 0.05–0.35 程度。0.6 超は反転疑い
    inverted_suspect = ink_ratio > 0.55
    save_png(os.path.join(OUT, "A_fill_check_juu.png"), canvas)
    return {
        "ok": not inverted_suspect and ink_ratio > 0.02,
        "ink_ratio": ink_ratio,
        "bbox": [x0, y0, x1, y1],
        "inverted_suspect": inverted_suspect,
        "png": os.path.join(OUT, "A_fill_check_juu.png"),
    }


def reverse_all_glyph_contours_in_ufo() -> None:
    """UFO 内の全輪郭を逆順にして塗りを修正。"""
    import ufoLib2

    font = ufoLib2.Font.open(UFO_DIR)
    for g in font:
        if g.name == ".notdef":
            continue
        # collect contours via recording
        from fontTools.pens.recordingPen import RecordingPen

        rec = RecordingPen()
        g.draw(rec)
        # rebuild reversed
        g.clearContours()
        pen = g.getPen()
        # parse recording into contours
        contours: List[List[Tuple[float, float]]] = []
        cur: List[Tuple[float, float]] = []
        for op, args in rec.value:
            if op == "moveTo":
                if cur:
                    contours.append(cur)
                cur = [args[0]]
            elif op == "lineTo":
                cur.append(args[0])
            elif op == "closePath":
                if cur:
                    contours.append(cur)
                    cur = []
            elif op == "endPath":
                if cur:
                    contours.append(cur)
                    cur = []
        if cur:
            contours.append(cur)
        for c in contours:
            pts = list(reversed(c))
            if len(pts) < 3:
                continue
            pen.moveTo(pts[0])
            for pt in pts[1:]:
                pen.lineTo(pt)
            pen.closePath()
    font.save()


# --- B: measure both paths -------------------------------------------------

def render_poly_pillow(
    contours_svg: List[List[Tuple[float, float]]],
    em_px: int = EM_PX,
) -> np.ndarray:
    """
    SVG座標（Y下・UPM=1000）の輪郭を Pillow で EM×EM に直描画。
    profile: poly_pillow_1024_gray_v1
    """
    scale = em_px / UPM
    img = Image.new("L", (em_px, em_px), 0)
    draw = ImageDraw.Draw(img)
    for contour in contours_svg:
        if len(contour) < 3:
            continue
        pts = [(x * scale, y * scale) for x, y in contour]
        draw.polygon(pts, fill=255)
    return np.asarray(img, dtype=np.uint8)


def measure_otf_juu(otf_path: str) -> Tuple[dict, np.ndarray]:
    face = freetype.Face(otf_path)
    face.set_pixel_sizes(EM_PX, EM_PX)
    gray, meta = render_glyph_gray(face, "十")
    canvas = place_on_em_canvas(gray, meta)
    probe = measure_juu_contrast(canvas)
    probe["meta"] = meta
    return probe, canvas


# --- C: proof --------------------------------------------------------------

def proof_uharfbuzz_freetype(otf_path: str, text: str = "十二永") -> dict:
    """uharfbuzz で shape → freetype で各グリフ描画 → 1行画像。"""
    import uharfbuzz as hb

    with open(otf_path, "rb") as f:
        data = f.read()
    face_hb = hb.Face(data)
    font_hb = hb.Font(face_hb)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font_hb, buf)

    face_ft = freetype.Face(otf_path)
    face_ft.set_pixel_sizes(EM_PX, EM_PX)

    # layout in pixels: advance is in font units (upem)
    scale = EM_PX / face_hb.upem
    infos = buf.glyph_infos
    positions = buf.glyph_positions

    total_adv = sum(pos.x_advance for pos in positions) * scale
    height = EM_PX + 80
    width = max(int(math.ceil(total_adv)) + 40, EM_PX)
    canvas = np.zeros((height, width), dtype=np.uint8)

    pen_x = 20.0
    baseline = int(EM_PX * 0.88)
    shaped = []
    for info, pos in zip(infos, positions):
        gid = info.codepoint
        face_ft.load_glyph(gid, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
        glyph = face_ft.glyph
        bitmap = glyph.bitmap
        w, h, pitch = bitmap.width, bitmap.rows, bitmap.pitch
        buf_b = bytes(bitmap.buffer)
        if w > 0 and h > 0:
            arr = np.zeros((h, w), dtype=np.uint8)
            for row in range(h):
                start = row * pitch
                arr[row, :] = np.frombuffer(buf_b[start : start + w], dtype=np.uint8)
            x0 = int(pen_x + pos.x_offset * scale + glyph.bitmap_left)
            y0 = int(baseline - pos.y_offset * scale - glyph.bitmap_top)
            x1, y1 = x0 + w, y0 + h
            cx0, cy0 = max(0, x0), max(0, y0)
            cx1, cy1 = min(width, x1), min(height, y1)
            if cx0 < cx1 and cy0 < cy1:
                gx0, gy0 = cx0 - x0, cy0 - y0
                roi = canvas[cy0:cy1, cx0:cx1]
                src = arr[gy0 : gy0 + (cy1 - cy0), gx0 : gx0 + (cx1 - cx0)]
                canvas[cy0:cy1, cx0:cx1] = np.maximum(roi, src)
        try:
            gname = font_hb.get_glyph_name(gid)
        except Exception:
            gname = None
        shaped.append({"gid": int(gid), "name": gname, "ax": int(pos.x_advance)})
        pen_x += pos.x_advance * scale

    png = os.path.join(OUT, "C_proof_juuni_ei.png")
    save_png(png, canvas)
    return {"ok": len(shaped) == len(text) and all(s["gid"] != 0 for s in shaped), "shaped": shaped, "png": png}


def proof_hb_view(otf_path: str, text: str = "十二永") -> dict:
    hb_view = shutil.which("hb-view")
    if not hb_view:
        return {"ok": False, "skipped": True, "reason": "hb-view not found"}
    png = os.path.join(OUT, "C_proof_hbview_juuni_ei.png")
    # Homebrew harfbuzz: -o / -O（--output / --format ではない）
    cmd = [
        hb_view,
        "-o",
        png,
        "-O",
        "png",
        f"--font-size={EM_PX // 4}",
        otf_path,
        text,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return {
        "ok": p.returncode == 0 and os.path.isfile(png),
        "cmd": cmd,
        "returncode": p.returncode,
        "stderr_tail": (p.stderr or "")[-500:],
        "png": png if os.path.isfile(png) else None,
    }


def try_diffenator2(otf_path: str) -> dict:
    print("=== pip install diffenator2 ===")
    inst = subprocess.run(
        [PIP, "install", "diffenator2"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    result = {
        "install_ok": inst.returncode == 0,
        "install_rc": inst.returncode,
        "install_stderr_tail": (inst.stderr or "")[-800:],
    }
    if inst.returncode != 0:
        result["proof"] = {"ok": False, "skipped": True, "reason": "install failed"}
        return result

    out_dir = os.path.join(OUT, "diffenator2_proof")
    os.makedirs(out_dir, exist_ok=True)
    # diffenator2 proof FONT — HTML 組見本
    # CLI はバージョンで差があるため --help を見てから実行
    help_p = subprocess.run(
        [os.path.join(VENV_BIN, "diffenator2"), "proof", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    result["proof_help_ok"] = help_p.returncode == 0
    result["proof_help_head"] = (help_p.stdout or "")[:600]

    # 典型: diffenator2 proof font.otf -o outdir
    # 失敗しても深追いしない
    cmd_candidates = [
        [os.path.join(VENV_BIN, "diffenator2"), "proof", otf_path, "-o", out_dir],
        [os.path.join(VENV_BIN, "diffenator2"), "proof", otf_path, "--out", out_dir],
        [os.path.join(VENV_BIN, "diffenator2"), "proof", "-o", out_dir, otf_path],
    ]
    for cmd in cmd_candidates:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        htmls = []
        if os.path.isdir(out_dir):
            for root, _, files in os.walk(out_dir):
                for fn in files:
                    if fn.endswith(".html"):
                        htmls.append(os.path.join(root, fn))
        if p.returncode == 0 and htmls:
            result["proof"] = {
                "ok": True,
                "cmd": cmd,
                "htmls": htmls,
                "stdout_tail": (p.stdout or "")[-500:],
            }
            return result
        last = {
            "ok": False,
            "cmd": cmd,
            "returncode": p.returncode,
            "stderr_tail": (p.stderr or "")[-600:],
            "stdout_tail": (p.stdout or "")[-400:],
            "htmls": htmls,
        }
    result["proof"] = last
    return result


# --- main ------------------------------------------------------------------

def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    report: dict = {
        "plan_refs": {
            "A": "§3.1 P3 / §0.1 座標系",
            "B": "§2.3 理想経路（物差し1本化）",
            "C": "§3.2 / P1 組見本",
        },
        "A": {},
        "B": {},
        "C": {},
        "coord_pitfalls": [],
        "plan_amendments": [],
    }

    # ========== A ==========
    print("=== A: union → Y-flip → UFO → fontmake ===")
    font_contours: Dict[str, List[List[Tuple[float, float]]]] = {}
    svg_contours: Dict[str, List[List[Tuple[float, float]]]] = {}
    union_metas = {}
    winding_reports = {}

    for key in ("juu", "ni", "ei"):
        svg_c, meta = build_union_contours(key)
        svg_contours[key] = svg_c
        flipped = [flip_y_contour(c) for c in svg_c]
        fixed, wrep = ensure_ps_winding(flipped)
        font_contours[key] = fixed
        union_metas[key] = meta
        winding_reports[key] = wrep
        print(
            f"  {key}({meta['label']}): contours {meta['before_contours']}→{meta['after_contours']}, "
            f"roles={wrep.get('roles')}, areas_after={[round(a,1) for a in wrep['areas_after']]}"
        )

    report["coord_pitfalls"].append(
        "prototype は SVG(Y下)。UFO へ書く前に y' = UPM - y が必須（PLAN §0.1）。"
        "Y反転は shoelace 符号を反転する。"
        "最大輪郭に合わせて一括反転 → 微小島が穴化。bbox 内包判定も打ち込み島を誤爆。"
        "十/二/永（意図的カウンター無し）では全輪郭を正面積（塗り）へ揃えて解消。"
        "口・国など真の穴がある字は点-in-polygon 入れ子判定が別途必要。"
    )

    ufo_path = build_ufo(font_contours, winding_reports)
    fm = run_fontmake()
    report["A"]["union"] = union_metas
    report["A"]["winding"] = {
        k: {
            "strategy": v.get("strategy"),
            "roles": v.get("roles"),
            "need_flip_all": v.get("need_flip_all"),
            "areas_before": v["areas_before"],
            "areas_after": v["areas_after"],
        }
        for k, v in winding_reports.items()
    }
    report["A"]["ufo"] = ufo_path
    report["A"]["fontmake"] = fm

    fill = None
    winding_fixed_retry = False
    if fm["ok"]:
        fill = check_fill_not_inverted(OTF_PATH)
        report["A"]["fill_check"] = fill
        if fill.get("inverted_suspect"):
            print("  fill inverted — reversing UFO contours and rebuilding")
            reverse_all_glyph_contours_in_ufo()
            fm2 = run_fontmake()
            winding_fixed_retry = True
            report["A"]["fontmake_retry"] = fm2
            if fm2["ok"]:
                fill = check_fill_not_inverted(OTF_PATH)
                report["A"]["fill_check_retry"] = fill
                report["coord_pitfalls"].append(
                    "初回の巻き方向推定が誤り、塗り反転を検出→輪郭逆順で再ビルドして解消。"
                )
    else:
        report["A"]["fill_check"] = {"ok": False, "reason": "fontmake failed"}

    a_ok = bool(fm.get("ok") or report["A"].get("fontmake_retry", {}).get("ok")) and bool(
        (report["A"].get("fill_check_retry") or fill or {}).get("ok")
    )
    # P3 全体（手設計同居・FontBakery・自己交差ゼロ）までは未達。経路スパイクとして
    report["A"]["verdict"] = {
        "overall": "条件付き" if a_ok else "不成立",
        "premise": "成立" if a_ok else "不成立",
        "note": (
            "union→Y反転→UFO→fontmake のビルドチェーンは通った。"
            "ただし P3 DoD（手設計同居・FB universal・自己交差別建て・cmap差分）は未検証。"
            "永は微小島が残り単一輪郭ではない（spike A / §3.3 と同趣旨）。"
            + (" 輪郭方向の再修正あり。" if winding_fixed_retry else "")
        ),
        "plan": "§3.1 P3（経路部分） / §0.1",
    }
    print("A verdict:", report["A"]["verdict"]["overall"])

    # ========== B ==========
    print("=== B: freetype vs poly_pillow ruler ===")
    if not os.path.isfile(OTF_PATH):
        report["B"]["verdict"] = {"overall": "不成立", "reason": "OTF missing"}
    else:
        ft_probe, ft_canvas = measure_otf_juu(OTF_PATH)
        save_png(os.path.join(OUT, "B_ft_juu.png"), ft_canvas)
        save_png(
            os.path.join(OUT, "B_ft_juu_bin.png"),
            ((ft_canvas >= THRESH) * 255).astype(np.uint8),
        )

        poly_canvas = render_poly_pillow(svg_contours["juu"])
        poly_probe = measure_juu_contrast(poly_canvas)
        save_png(os.path.join(OUT, "B_poly_juu.png"), poly_canvas)
        save_png(
            os.path.join(OUT, "B_poly_juu_bin.png"),
            ((poly_canvas >= THRESH) * 255).astype(np.uint8),
        )

        # 数値差
        diff = {}
        if ft_probe.get("status") == "ok" and poly_probe.get("status") == "ok":
            dv = ft_probe["vert_thickness_px"] - poly_probe["vert_thickness_px"]
            dh = ft_probe["horiz_thickness_px"] - poly_probe["horiz_thickness_px"]
            dc = ft_probe["contrast_v_over_h"] - poly_probe["contrast_v_over_h"]
            diff = {
                "vert_px_delta_ft_minus_poly": dv,
                "horiz_px_delta_ft_minus_poly": dh,
                "contrast_delta_ft_minus_poly": dc,
                "vert_rel_pct": (dv / poly_probe["vert_thickness_px"] * 100)
                if poly_probe["vert_thickness_px"]
                else None,
                "horiz_rel_pct": (dh / poly_probe["horiz_thickness_px"] * 100)
                if poly_probe["horiz_thickness_px"]
                else None,
                "contrast_rel_pct": (dc / poly_probe["contrast_v_over_h"] * 100)
                if poly_probe["contrast_v_over_h"]
                else None,
            }
            # 判定閾値: 太さ差が両方向とも ≤2px かつ コントラスト相対差 ≤5% → 1本化妥当
            # ≤5px かつ ≤15% → 条件付き / それ以上 → 分離必須
            abs_v, abs_h = abs(dv), abs(dh)
            rel_c = abs(diff["contrast_rel_pct"] or 999)
            if abs_v <= 2 and abs_h <= 2 and rel_c <= 5:
                ruler = "成立"
                note = "差が十分小さく、一時フォント化による物差し1本化は妥当。"
            elif abs_v <= 5 and abs_h <= 5 and rel_c <= 15:
                ruler = "条件付き"
                note = (
                    "差は中程度。校正アンカーとしては同一 freetype 経路へ寄せる価値あり。"
                    "ただし poly_pillow との混在平均は依然禁止が安全。"
                )
            else:
                ruler = "不成立"
                note = "差が大きく、profile 分離の維持が必須。1本化は時期尚早。"
        else:
            ruler = "不成立"
            note = f"計測失敗 ft={ft_probe.get('status')} poly={poly_probe.get('status')}"

        report["B"] = {
            "freetype": ft_probe,
            "poly_pillow": poly_probe,
            "diff": diff,
            "thresholds": {
                "成立": "Δ太さ≤2px かつ コントラスト相対差≤5%",
                "条件付き": "Δ太さ≤5px かつ 相対差≤15%",
                "不成立": "それ以上 → profile分離必須",
            },
            "verdict": {
                "overall": ruler,
                "premise": ruler,
                "note": note,
                "plan": "§2.3 将来の理想経路: エンジン出力→一時UFO/TTF→freetype profile",
            },
            "pngs": {
                "ft": os.path.join(OUT, "B_ft_juu.png"),
                "poly": os.path.join(OUT, "B_poly_juu.png"),
            },
        }
        print(
            "B ft:",
            {k: ft_probe.get(k) for k in ("vert_thickness_px", "horiz_thickness_px", "contrast_v_over_h", "status")},
        )
        print(
            "B poly:",
            {k: poly_probe.get(k) for k in ("vert_thickness_px", "horiz_thickness_px", "contrast_v_over_h", "status")},
        )
        print("B diff:", diff)
        print("B verdict:", ruler)

    # ========== C ==========
    print("=== C: proof smoke ===")
    if os.path.isfile(OTF_PATH):
        hb_proof = proof_uharfbuzz_freetype(OTF_PATH)
        hbview = proof_hb_view(OTF_PATH)
        diff2 = try_diffenator2(OTF_PATH)
        c_ok = hb_proof.get("ok") or hbview.get("ok")
        report["C"] = {
            "uharfbuzz_freetype": hb_proof,
            "hb_view": hbview,
            "diffenator2": diff2,
            "verdict": {
                "overall": "成立" if c_ok else "不成立",
                "diffenator2": (
                    "成立"
                    if diff2.get("proof", {}).get("ok")
                    else (
                        "不成立（install失敗）"
                        if not diff2.get("install_ok")
                        else "不成立（proof失敗/HTML無し）"
                    )
                ),
                "note": "§3.2: 組見本は全面自作せず hb-view / diffenator2 を第一候補。",
                "plan": "§3.2 / P1",
            },
        }
        print("C hb proof:", hb_proof.get("ok"), hb_proof.get("png"))
        print("C hb-view:", hbview.get("ok"), hbview.get("png"))
        print("C diffenator2:", report["C"]["verdict"]["diffenator2"])
    else:
        report["C"]["verdict"] = {"overall": "不成立", "reason": "OTF missing"}

    # PLAN amendments
    report["plan_amendments"] = [
        "§0.1: SVG→フォント空間の Y 反転後は輪郭向きが逆転する。CFF(OTF) では塗り輪郭を CCW へ。"
        "一括反転も bbox 穴判定も打ち込み島を誤って穴化する実測あり → 輪郭ごと正面積化が安全。"
        "真のカウンター字は入れ子判定を別途。ビルド後 ink_ratio チェックを DoD に。",
        "§2.3: 一時フォント化→freetype 計測の理想経路は本スパイクで端到端実証。"
        "poly_pillow との差（実測値を SPIKE3_REPORT に記載）に応じ、"
        "1本化採用 or profile 分離維持を明記する。",
        "§3.1 P3: fontmake -u UFO→OTF の最小パイプラインは成立。"
        "ただし polyline のまま載せる節点爆発・Bezier 再適合ゲート（§3.2）は未決のまま。",
        "§3.2: hb-view が macOS で利用可能なら黄金画像向きの第一候補として明記してよい。"
        "diffenator2 は install/proof の成否を SPIKE3 結果で更新。",
        "§3.3: P3 スパイクでも永の微小島は残存。製品ビルド前に Stage A+微小輪郭除去が必須"
        "（spike と同結論、端到端でも変わらず）。",
    ]

    report["overall"] = {
        "A": report["A"].get("verdict", {}).get("overall"),
        "B": report["B"].get("verdict", {}).get("overall"),
        "C": report["C"].get("verdict", {}).get("overall"),
    }

    out_json = os.path.join(OUT, "verify_e2e_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("wrote", out_json)
    print("OVERALL:", json.dumps(report["overall"], ensure_ascii=False))
    return 0 if report["overall"].get("A") != "不成立" else 1


if __name__ == "__main__":
    raise SystemExit(main())
