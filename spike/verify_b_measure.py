#!/usr/bin/env python3
"""B: freetype-py で実フォント計測（十のコントラスト・三のうろこ簡易検出）。"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional, Tuple

import freetype
import numpy as np
from PIL import Image

SPIKE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SPIKE, "output")
FONTS = os.path.join(SPIKE, "fonts")
EM_PX = 1024
THRESH = 128


def find_font() -> Tuple[str, str, Optional[int]]:
    """
    戻り値: (path, source_label, face_index or None)
    GitHub 由来を優先。失敗時はヒラギノ（参考扱い）。
    """
    # 静的インスタンス（wght=400）を最優先
    instanced = os.path.join(FONTS, "NotoSerifJP-Regular-wght400.ttf")
    if os.path.isfile(instanced) and os.path.getsize(instanced) > 1000:
        return instanced, "google/fonts NotoSerifJP variable → fontTools instancer wght=400", 0

    candidates = [
        (os.path.join(FONTS, "NotoSerifJP-Regular.otf"), "google/fonts NotoSerifJP variable (default=ExtraLight)"),
        (os.path.join(FONTS, "NotoSerifCJKjp-Regular.otf"), "noto-cjk OTF"),
        (os.path.join(FONTS, "SourceHanSerifJP-Regular.otf"), "source-han-serif"),
    ]
    for path, label in candidates:
        if os.path.isfile(path) and os.path.getsize(path) > 1000:
            return path, label, 0

    hira = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
    if os.path.isfile(hira):
        return hira, "macOS ヒラギノ明朝 ProN.ttc（参考扱い・計測コード動作確認のみ）", 0
    raise FileNotFoundError("日本語明朝フォントが見つかりません")


def load_face(path: str, face_index: int = 0) -> freetype.Face:
    face = freetype.Face(path, index=face_index)
    # 可変フォントは default=ExtraLight(200) になりやすい → Regular(400) を明示
    try:
        info = face.get_variation_info()
        axes = getattr(info, "axes", None) or []
        tags = []
        for ax in axes:
            tag = ax.tag if hasattr(ax, "tag") else (ax[0] if isinstance(ax, (tuple, list)) else None)
            tags.append(tag)
        if any(t == b"wght" or t == "wght" for t in tags):
            # set_var_design_coords は軸順のリスト
            coords = []
            for ax in axes:
                tag = ax.tag if hasattr(ax, "tag") else ax[0]
                if tag in (b"wght", "wght"):
                    coords.append(400.0)
                else:
                    default = ax.default if hasattr(ax, "default") else ax[2]
                    coords.append(float(default))
            face.set_var_design_coords(coords)
    except Exception:
        pass
    # 1024 px/EM: set_pixel_sizes で直接指定（set_char_size の pt/dpi 換算を避ける）
    face.set_pixel_sizes(EM_PX, EM_PX)
    return face


def render_glyph_gray(face: freetype.Face, char: str) -> Tuple[np.ndarray, dict]:
    """FT_LOAD_NO_HINTING + グレー AA。Y 下向きの画像配列 (H,W) uint8。"""
    flags = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER
    # FT_LOAD_TARGET_NORMAL がデフォのグレー AA
    face.load_char(char, flags)
    glyph = face.glyph
    bitmap = glyph.bitmap
    w, h = bitmap.width, bitmap.rows
    pitch = bitmap.pitch
    buf = bytes(bitmap.buffer)
    meta = {
        "width": w,
        "rows": h,
        "pitch": pitch,
        "pixel_mode": int(bitmap.pixel_mode),
        "left": glyph.bitmap_left,
        "top": glyph.bitmap_top,
        "advance_x": glyph.advance.x / 64.0,
        "units_per_EM": face.units_per_EM,
    }
    if w == 0 or h == 0:
        return np.zeros((0, 0), dtype=np.uint8), meta

    # pitch は行バイト数（正=左→右、上→下）。gray は 1 byte/pixel。
    arr = np.zeros((h, w), dtype=np.uint8)
    for row in range(h):
        start = row * pitch
        # pitch が w より大きい場合パディングあり。負 pitch は下→上（稀）
        if pitch >= w:
            row_bytes = buf[start : start + w]
        else:
            # 想定外: 可能な範囲で読む
            row_bytes = buf[start : start + max(0, pitch)]
            row_bytes = row_bytes.ljust(w, b"\x00")[:w]
        arr[row, :] = np.frombuffer(row_bytes, dtype=np.uint8)
    return arr, meta


def place_on_em_canvas(gray: np.ndarray, meta: dict) -> np.ndarray:
    """
    グリフビットマップを EM×EM キャンバスに配置。
    FreeType: bitmap_top は baseline からの上方向距離、bitmap_left は左方向。
    baseline を canvas の下から descender 分… ここでは簡易に
    「字面がキャンバス中央付近に来る」よう top-left を:
      x = (EM - advance)/2 + bitmap_left は複雑なので、
      PLAN プロトコル準拠: 原点を左上、baseline を EM*0.8 付近に置く慣例、
      ここでは face 非依存に bitmap を「字面中央」計測できるよう
      キャンバス中央に bbox 中心を合わせて配置する。
    """
    canvas = np.zeros((EM_PX, EM_PX), dtype=np.uint8)
    h, w = gray.shape if gray.size else (0, 0)
    if h == 0 or w == 0:
        return canvas
    # baseline ベース配置（標準）
    # y: baseline = round(EM * 0.88) 近似（CJK はほぼ正方形）
    baseline = int(EM_PX * 0.88)
    x0 = (EM_PX - int(meta["advance_x"])) // 2 + int(meta["left"])
    y0 = baseline - int(meta["top"])
    # クリップコピー
    x1, y1 = x0 + w, y0 + h
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(EM_PX, x1), min(EM_PX, y1)
    gx0, gy0 = cx0 - x0, cy0 - y0
    canvas[cy0:cy1, cx0:cx1] = gray[gy0 : gy0 + (cy1 - cy0), gx0 : gx0 + (cx1 - cx0)]
    return canvas


def longest_run(binary_row: np.ndarray) -> int:
    best = cur = 0
    for v in binary_row:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def measure_juu_contrast(canvas: np.ndarray) -> dict:
    """
    字面中央付近の走査で縦画・横画太さを測る。
    交点そのものでは垂直走査が縦画の長さを拾うため、
    縦画太さは交点の上下、横画太さは交点の左右で測る。
    """
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty"}
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    face_h = y_max - y_min + 1
    face_w = x_max - x_min + 1

    # 縦画太さ: 交点の上側・下側で水平走査（縦画だけを横切る）
    vert_cands = []
    for dy in (-int(face_h * 0.22), -int(face_h * 0.15), int(face_h * 0.15), int(face_h * 0.22)):
        yy = cy + dy
        if 0 <= yy < EM_PX:
            run = longest_run(bin_img[yy, x_min : x_max + 1])
            if 2 <= run < face_w * 0.35:
                vert_cands.append(run)

    # 横画太さ: 交点の左右で垂直走査（横画だけを横切る）
    horiz_cands = []
    for dx in (-int(face_w * 0.22), -int(face_w * 0.15), int(face_w * 0.15), int(face_w * 0.22)):
        xx = cx + dx
        if 0 <= xx < EM_PX:
            run = longest_run(bin_img[y_min : y_max + 1, xx])
            if 2 <= run < face_h * 0.35:
                horiz_cands.append(run)

    if not vert_cands or not horiz_cands:
        return {
            "status": "low_confidence",
            "reason": "scan candidates empty",
            "vert_cands": vert_cands,
            "horiz_cands": horiz_cands,
            "bbox": [x_min, y_min, x_max, y_max],
        }

    vert_thickness_px = float(np.median(vert_cands))
    horiz_thickness_px = float(np.median(horiz_cands))
    contrast = vert_thickness_px / horiz_thickness_px if horiz_thickness_px > 0 else None

    return {
        "status": "ok",
        "bbox": [x_min, y_min, x_max, y_max],
        "scan_center": [cx, cy],
        "vert_thickness_px": vert_thickness_px,
        "horiz_thickness_px": horiz_thickness_px,
        "vert_thickness_em": vert_thickness_px / EM_PX,
        "horiz_thickness_em": horiz_thickness_px / EM_PX,
        "contrast_v_over_h": contrast,
        "vert_cands": vert_cands,
        "horiz_cands": horiz_cands,
        "face_w": face_w,
        "face_h": face_h,
    }


def measure_san_uroko(canvas: np.ndarray) -> dict:
    """
    「三」上横画右端のうろこ突出を簡易検出。
    上側 35% のインク帯で右端付近の上方向突出（横画上面より上のインク）を測る。
    """
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty"}
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    face_h = y_max - y_min + 1
    # 上横画 ROI: 上部 30%
    y_lo = y_min
    y_hi = y_min + max(8, int(face_h * 0.28))
    roi = bin_img[y_lo:y_hi, x_min : x_max + 1]
    if roi.size == 0:
        return {"status": "fail", "reason": "empty roi"}

    # 各列の最上インク y
    col_top = []
    for c in range(roi.shape[1]):
        col = roi[:, c]
        ink = np.where(col)[0]
        if len(ink):
            col_top.append((c, int(ink.min()), int(ink.max())))
    if len(col_top) < 10:
        return {"status": "low_confidence", "reason": "few columns"}

    # 横画本体の上面 y（中央 40–70% 列の中央値）
    n = len(col_top)
    mid = col_top[int(n * 0.4) : int(n * 0.7)]
    body_top = float(np.median([t for _, t, _ in mid]))
    body_bot = float(np.median([b for _, _, b in mid]))
    body_thick = body_bot - body_top + 1

    # 右端 15% 列での上面が body_top より上（画像座標では小さい）に出ている量
    right = col_top[int(n * 0.85) :]
    if not right:
        return {"status": "low_confidence", "reason": "no right cols"}
    right_top = min(t for _, t, _ in right)
    protrusion_px = max(0.0, body_top - right_top)
    # 右端の縦方向インク長が本体より長い場合もうろこ候補
    right_heights = [b - t + 1 for _, t, b in right]
    height_boost = max(0.0, float(np.max(right_heights)) - body_thick)

    return {
        "status": "ok",
        "body_thickness_px": body_thick,
        "uroko_protrusion_px": protrusion_px,
        "uroko_height_boost_px": height_boost,
        "uroko_protrusion_em": protrusion_px / EM_PX,
        "uroko_relative_to_stroke": (protrusion_px / body_thick) if body_thick > 0 else None,
        "roi": [x_min, y_lo, x_max, y_hi],
        "note": "簡易検出。様式的ゼロと検出不能の区別は閾値設計が必要（PLAN §2.4）",
    }


def save_png(path: str, canvas: np.ndarray) -> None:
    Image.fromarray(canvas, mode="L").save(path)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    font_path, label, idx = find_font()
    print(f"font: {font_path}")
    print(f"source: {label}")

    is_reference = "参考" in label
    face = load_face(font_path, idx or 0)
    print(
        f"family={face.family_name} style={face.style_name} "
        f"upem={face.units_per_EM} faces_in_file≈(ttc index={idx})"
    )

    report = {
        "font_path": font_path,
        "source": label,
        "reference_only": is_reference,
        "units_per_EM": face.units_per_EM,
        "family": face.family_name.decode() if isinstance(face.family_name, bytes) else str(face.family_name),
        "style": face.style_name.decode() if isinstance(face.style_name, bytes) else str(face.style_name),
        "protocol": {
            "em_px": EM_PX,
            "load_flags": "FT_LOAD_NO_HINTING | FT_LOAD_RENDER",
            "threshold": THRESH,
            "plan_refs": ["§2.3 ft_1024_nohint_gray_v1", "§2.4 Phase α juu_contrast / san_uroko"],
        },
        "glyphs": {},
        "pitfalls": [],
    }

    # pitch / origin notes
    report["pitfalls"].extend(
        [
            "TTC は Face(path, index=N) でフェイス選択。ヒラギノは複数スタイルが入る",
            "set_pixel_sizes(EM, EM) で 1024px/EM。set_char_size は pt/dpi 換算で誤りやすい",
            "bitmap.pitch は行ストライド（>= width）。必ず pitch で行送りすること",
            "bitmap_top は baseline からの上方向、画像行は下向き。配置時に y0=baseline-top",
            "FT_LOAD_NO_HINTING 無しだとヒントで太さが変わり T3 の黄金画像が不安定",
            "可変フォントはデフォルトインスタンス（wght 軸の初期値）でラスタ化される点に注意",
        ]
    )

    for ch, name in [("十", "juu"), ("三", "san"), ("二", "ni")]:
        gray, meta = render_glyph_gray(face, ch)
        canvas = place_on_em_canvas(gray, meta)
        png = os.path.join(OUT, f"raster_{name}_{EM_PX}.png")
        save_png(png, canvas)
        # 二値化プレビュー
        bin_png = os.path.join(OUT, f"raster_{name}_{EM_PX}_bin.png")
        save_png(bin_png, ((canvas >= THRESH) * 255).astype(np.uint8))

        entry = {"meta": meta, "png": png, "bin_png": bin_png}
        if ch == "十":
            entry["probe"] = measure_juu_contrast(canvas)
        elif ch in ("三", "二"):
            entry["probe"] = measure_san_uroko(canvas)
        report["glyphs"][name] = entry
        print(name, json.dumps(entry["probe"], ensure_ascii=False))

    # 判定
    juu = report["glyphs"]["juu"]["probe"]
    san = report["glyphs"]["san"]["probe"]
    protocol_ok = juu.get("status") == "ok" and juu.get("contrast_v_over_h") is not None
    uroko_tried = san.get("status") in ("ok", "low_confidence")
    if protocol_ok and uroko_tried:
        verdict = "成立" if not is_reference else "条件付き（参考フォント）"
    elif protocol_ok:
        verdict = "条件付き"
    else:
        verdict = "不成立"
    report["verdict"] = {
        "overall": verdict,
        "juu_contrast_ok": protocol_ok,
        "san_uroko_tried": uroko_tried,
        "plan": "§2.3/§2.4 計測プロトコルは実装可能",
    }

    out_json = os.path.join(OUT, "verify_b_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("VERDICT:", verdict)
    print("wrote", out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
