#!/usr/bin/env python3
"""
spike4: fontdb MVP 縮小実装（T2〜T6 実証）
- schema.sql 適用
- 取得済み全書体 × 代表字 glyph_metric
- juu_contrast / san_uroko probe
- コントラスト×うろこ 散布図
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import freetype
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DB = ROOT / "data" / "fontdb.sqlite"
SCHEMA = ROOT / "schemas" / "schema.sql"
CORPUS = ROOT / "corpus_actual.yaml"

EM_PX = 1024
THRESH = 128
PROFILE_ID = "ft_1024_nohint_gray_v1"
EXTRACTOR = "spike4_v1"

# 代表字（PLAN 指示）
GLYPHS = list("三十口田国日東鬱永あのん")


def load_face(path: str) -> freetype.Face:
    face = freetype.Face(path)
    try:
        info = face.get_variation_info()
        axes = getattr(info, "axes", None) or []
        if axes:
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
    face.set_pixel_sizes(EM_PX, EM_PX)
    return face


def render_glyph_gray(face: freetype.Face, char: str) -> tuple[np.ndarray, dict]:
    flags = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER
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
        "left": glyph.bitmap_left,
        "top": glyph.bitmap_top,
        "advance_x": glyph.advance.x / 64.0,
        "units_per_EM": face.units_per_EM,
    }
    if w == 0 or h == 0:
        return np.zeros((0, 0), dtype=np.uint8), meta
    arr = np.zeros((h, w), dtype=np.uint8)
    for row in range(h):
        start = row * pitch
        if pitch >= w:
            row_bytes = buf[start : start + w]
        else:
            row_bytes = buf[start : start + max(0, pitch)].ljust(w, b"\x00")[:w]
        arr[row, :] = np.frombuffer(row_bytes, dtype=np.uint8)
    return arr, meta


def place_on_em_canvas(gray: np.ndarray, meta: dict) -> np.ndarray:
    canvas = np.zeros((EM_PX, EM_PX), dtype=np.uint8)
    h, w = gray.shape if gray.size else (0, 0)
    if h == 0 or w == 0:
        return canvas
    baseline = int(EM_PX * 0.88)
    x0 = (EM_PX - int(meta["advance_x"])) // 2 + int(meta["left"])
    y0 = baseline - int(meta["top"])
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


def ink_metrics(canvas: np.ndarray) -> dict:
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "missing" if canvas.max() == 0 else "fail", "reason": "empty"}
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    area = bw * bh
    ink = int(bin_img[y0 : y1 + 1, x0 : x1 + 1].sum())
    # centroid in EM coords (x right, y down as image; report as em fractions)
    cy_i, cx_i = np.mean(ys), np.mean(xs)
    return {
        "status": "ok",
        "ink_bbox": [x0, y0, x1, y1],
        "face_ratio": area / (EM_PX * EM_PX),
        "black_density": ink / area if area else None,
        "centroid_x_em": float(cx_i) / EM_PX,
        "centroid_y_em": float(cy_i) / EM_PX,
        "ink_pixels": ink,
    }


def measure_juu_contrast(canvas: np.ndarray) -> dict:
    """交点回避走査（spike 実証済み）。"""
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty", "value": None}
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    face_h = y_max - y_min + 1
    face_w = x_max - x_min + 1

    vert_cands = []
    for dy in (-int(face_h * 0.22), -int(face_h * 0.15), int(face_h * 0.15), int(face_h * 0.22)):
        yy = cy + dy
        if 0 <= yy < EM_PX:
            run = longest_run(bin_img[yy, x_min : x_max + 1])
            if 2 <= run < face_w * 0.35:
                vert_cands.append(run)

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
            "value": None,
            "vert_cands": vert_cands,
            "horiz_cands": horiz_cands,
        }

    vert = float(np.median(vert_cands))
    horiz = float(np.median(horiz_cands))
    contrast = vert / horiz if horiz > 0 else None
    return {
        "status": "ok",
        "value": contrast,
        "value_secondary": horiz,
        "vert_thickness_px": vert,
        "horiz_thickness_px": horiz,
        "contrast_v_over_h": contrast,
        "vert_cands": vert_cands,
        "horiz_cands": horiz_cands,
    }


def measure_san_uroko(canvas: np.ndarray) -> dict:
    """
    三のうろこ: 水平投影ピーク検出 → 上横画帯 ROI → 右端突出高さ。
    書体別チューニングなしの共通閾値で status を判定。
    """
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty", "value": None}

    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    face_h = y_max - y_min + 1
    face_w = x_max - x_min + 1
    glyph = bin_img[y_min : y_max + 1, x_min : x_max + 1]

    # 1) 水平投影（行ごとのインク量）でピーク検出 → 上横画帯
    row_proj = glyph.sum(axis=1).astype(float)
    # 平滑化
    kernel = np.ones(5) / 5.0
    smooth = np.convolve(row_proj, kernel, mode="same")
    # 上部 45% 内のピークを上横画候補とする
    top_cut = max(8, int(face_h * 0.45))
    top_region = smooth[:top_cut]
    if top_region.max() < 3:
        return {"status": "fail", "reason": "no top stroke peak", "value": None}

    peak_y = int(np.argmax(top_region))
    peak_val = float(top_region[peak_y])
    # ピーク周辺で投影がピークの 45% 以上の帯
    thresh_proj = peak_val * 0.45
    lo = peak_y
    while lo > 0 and smooth[lo - 1] >= thresh_proj:
        lo -= 1
    hi = peak_y
    while hi < top_cut - 1 and smooth[hi + 1] >= thresh_proj:
        hi += 1
    # 帯が薄すぎる/厚すぎる場合はフォールバック（上部 28%）
    band_h = hi - lo + 1
    used_fallback = False
    if band_h < 4 or band_h > face_h * 0.22:
        used_fallback = True
        lo = 0
        hi = max(8, int(face_h * 0.28)) - 1

    # 帯の上下に少しマージン（突出検出用）
    margin = max(4, int(band_h * 0.8))
    y_lo = max(0, lo - margin)
    y_hi = min(face_h - 1, hi + max(2, band_h // 3))
    roi = glyph[y_lo : y_hi + 1, :]

    # 2) 各列の最上インク（ROI 内相対 y）
    col_top = []
    col_bot = []
    for c in range(roi.shape[1]):
        ink = np.where(roi[:, c])[0]
        if len(ink):
            col_top.append(int(ink.min()))
            col_bot.append(int(ink.max()))
        else:
            col_top.append(-1)
            col_bot.append(-1)

    valid = [i for i, t in enumerate(col_top) if t >= 0]
    if len(valid) < max(10, int(face_w * 0.3)):
        return {
            "status": "low_confidence",
            "reason": "few ink columns in top stroke ROI",
            "value": None,
            "peak_y_rel": peak_y,
            "used_fallback_band": used_fallback,
        }

    # 本体上面: 中央 35–70% 列
    mid_cols = [c for c in valid if 0.35 * face_w <= c <= 0.70 * face_w]
    if len(mid_cols) < 5:
        mid_cols = valid[int(len(valid) * 0.35) : int(len(valid) * 0.70)]
    if not mid_cols:
        return {"status": "low_confidence", "reason": "no mid columns", "value": None}

    body_top = float(np.median([col_top[c] for c in mid_cols]))
    body_bot = float(np.median([col_bot[c] for c in mid_cols]))
    body_thick = body_bot - body_top + 1
    if body_thick < 2:
        return {
            "status": "low_confidence",
            "reason": "body thickness < 2px",
            "value": None,
            "body_thickness_px": body_thick,
        }

    # 3) 右端 ROI（右 12%）での突出
    right_cols = [c for c in valid if c >= int(face_w * 0.88)]
    if len(right_cols) < 3:
        right_cols = valid[int(len(valid) * 0.88) :]
    if not right_cols:
        return {"status": "low_confidence", "reason": "no right columns", "value": None}

    right_top = min(col_top[c] for c in right_cols)
    protrusion_px = max(0.0, body_top - right_top)
    right_heights = [col_bot[c] - col_top[c] + 1 for c in right_cols]
    height_boost = max(0.0, float(np.max(right_heights)) - body_thick)
    # 相対値: 突出 / 本体太さ（主要指標）
    relative = protrusion_px / body_thick if body_thick > 0 else 0.0

    # 共通判定（書体別チューニングなし）
    # - 突出が明確: relative >= 0.15 かつ protrusion >= 3px → ok
    # - 様式的ゼロ候補: relative < 0.08 かつ protrusion < 2 → ok (value≈0)
    # - 中間帯: low_confidence（検出揺らぎ）
    detail = {
        "body_thickness_px": body_thick,
        "uroko_protrusion_px": protrusion_px,
        "uroko_height_boost_px": height_boost,
        "uroko_relative_to_stroke": relative,
        "peak_y_rel": peak_y,
        "band_lo_hi": [lo, hi],
        "roi_y_abs": [y_min + y_lo, y_min + y_hi],
        "used_fallback_band": used_fallback,
        "right_top_rel": right_top,
        "body_top_rel": body_top,
    }

    if protrusion_px >= 3.0 and relative >= 0.15:
        status, reason = "ok", "clear uroko protrusion"
    elif protrusion_px < 2.0 and relative < 0.08:
        # 様式的ゼロも ok（PLAN §2.4: うろこ無しは value≈0 の正常値）
        status, reason = "ok", "stylistic zero or negligible uroko (value≈0)"
    elif height_boost >= 4.0 and relative >= 0.10:
        status, reason = "ok", "accepted via height_boost"
    else:
        status, reason = (
            "low_confidence",
            f"ambiguous protrusion (px={protrusion_px:.1f}, rel={relative:.3f}, boost={height_boost:.1f})",
        )

    return {
        "status": status,
        "reason": reason,
        "value": relative,
        "value_secondary": protrusion_px,
        **detail,
    }


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT OR REPLACE INTO render_profile VALUES (?,?,?,?,?,?,?)",
        (PROFILE_ID, EM_PX, "off", "gray", THRESH, "image_down", "PLAN §2.3"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO extractor VALUES (?,?)",
        (EXTRACTOR, "spike4 MVP: glyph ink + juu_contrast + san_uroko"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO probe_def VALUES (?,?,?,?)",
        ("juu_contrast", "十", "alpha", "縦/横コントラスト（交点回避走査）"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO probe_def VALUES (?,?,?,?)",
        ("san_uroko", "三", "alpha", "三の上横画右端うろこ相対サイズ"),
    )
    conn.commit()


def codepoint(ch: str) -> str:
    return f"U+{ord(ch):04X}"


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    with open(CORPUS, encoding="utf-8") as f:
        corpus = yaml.safe_load(f)

    families = [x for x in corpus["families"] if x.get("acquired")]
    if not families:
        raise SystemExit("no acquired fonts in corpus_actual.yaml — run fetch_corpus.py first")

    conn = sqlite3.connect(DB)
    init_db(conn)

    report: dict[str, Any] = {
        "profile": PROFILE_ID,
        "extractor": EXTRACTOR,
        "glyphs": GLYPHS,
        "faces": {},
        "probe_summary": [],
        "san_uroko_stability": {},
    }

    scatter_rows = []  # (family_label, contrast, uroko_rel, juu_status, san_status)

    for fam in families:
        fid = fam["family_id"]
        path = ROOT / fam["path_rel"]
        print(f"\n--- measure {fid} ---")
        face_ft = load_face(str(path))
        family_name = face_ft.family_name
        if isinstance(family_name, bytes):
            family_name = family_name.decode("utf-8", "replace")
        style_name = face_ft.style_name
        if isinstance(style_name, bytes):
            style_name = style_name.decode("utf-8", "replace")

        conn.execute(
            "INSERT OR REPLACE INTO family VALUES (?,?,?,?,?)",
            (fid, fam["display_name"], fam["license"], fam.get("vendor"), fam.get("notes")),
        )
        face_id = f"{fid}_regular"
        conn.execute(
            "INSERT OR REPLACE INTO face VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                face_id,
                fid,
                "opentype",
                style_name or "Regular",
                400,
                1 if fam.get("is_variable") else 0,
                json.dumps(fam.get("instance_coords")) if fam.get("instance_coords") else None,
                fam["path_rel"],
                fam["sha256_measured"],
                fam.get("source_url"),
                fam.get("units_per_em") or face_ft.units_per_EM,
            ),
        )

        face_report: dict[str, Any] = {"path": fam["path_rel"], "glyphs": {}, "probes": {}}
        # glyph metrics
        canvases: dict[str, np.ndarray] = {}
        for ch in GLYPHS:
            gray, meta = render_glyph_gray(face_ft, ch)
            # 欠字: index 0 (.notdef) や空ビットマップ
            gid = face_ft.get_char_index(ord(ch))
            canvas = place_on_em_canvas(gray, meta)
            canvases[ch] = canvas
            m = ink_metrics(canvas)
            if gid == 0:
                m = {"status": "missing", "reason": "cmap missing (gid=0)"}
            status = m["status"]
            bbox = m.get("ink_bbox")
            conn.execute(
                """INSERT OR REPLACE INTO glyph_metric VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    face_id,
                    codepoint(ch),
                    ch,
                    PROFILE_ID,
                    EXTRACTOR,
                    status,
                    bbox[0] if bbox else None,
                    bbox[1] if bbox else None,
                    bbox[2] if bbox else None,
                    bbox[3] if bbox else None,
                    m.get("face_ratio"),
                    m.get("black_density"),
                    m.get("centroid_x_em"),
                    m.get("centroid_y_em"),
                    meta.get("advance_x"),
                ),
            )
            face_report["glyphs"][ch] = {
                "status": status,
                "face_ratio": m.get("face_ratio"),
                "black_density": m.get("black_density"),
                "centroid": [m.get("centroid_x_em"), m.get("centroid_y_em")],
            }
            # debug rasters for 十/三
            if ch in ("十", "三"):
                Image.fromarray(canvas, mode="L").save(OUT / f"raster_{fid}_{ch}.png")
                Image.fromarray(((canvas >= THRESH) * 255).astype(np.uint8), mode="L").save(
                    OUT / f"raster_{fid}_{ch}_bin.png"
                )

        # probes
        juu = measure_juu_contrast(canvases["十"])
        san = measure_san_uroko(canvases["三"])
        for probe_id, res in (("juu_contrast", juu), ("san_uroko", san)):
            conn.execute(
                """INSERT OR REPLACE INTO probe_metric VALUES
                (?,?,?,?,?,?,?,?,?)""",
                (
                    face_id,
                    probe_id,
                    PROFILE_ID,
                    EXTRACTOR,
                    res["status"],
                    res.get("value"),
                    res.get("value_secondary"),
                    json.dumps({k: v for k, v in res.items() if k not in ("status",)}, ensure_ascii=False, default=str),
                    res.get("reason"),
                ),
            )
            face_report["probes"][probe_id] = res
            print(f"  {probe_id}: {res['status']} value={res.get('value')} reason={res.get('reason')}")

        report["faces"][fid] = face_report
            # 散布図ラベルは CJK 欠字回避のため family_id を短く
        short_label = {
            "source_han_serif_jp": "SourceHanSerifJP",
            "ipaex_mincho": "IPAexMincho",
            "shippori_mincho": "ShipporiMincho",
            "zen_old_mincho": "ZenOldMincho",
            "biz_ud_mincho": "BIZ UDMincho",
        }.get(fid, fid)
        scatter_rows.append(
            {
                "family_id": fid,
                "label": short_label,
                "display_name": fam["display_name"],
                "contrast": juu.get("contrast_v_over_h") or juu.get("value"),
                "uroko_rel": san.get("uroko_relative_to_stroke") if san.get("uroko_relative_to_stroke") is not None else san.get("value"),
                "uroko_px": san.get("uroko_protrusion_px"),
                "juu_status": juu["status"],
                "san_status": san["status"],
                "san_reason": san.get("reason"),
            }
        )
        report["probe_summary"].append(scatter_rows[-1])

    conn.commit()

    # san_uroko stability
    ok_n = sum(1 for r in scatter_rows if r["san_status"] == "ok")
    report["san_uroko_stability"] = {
        "ok_count": ok_n,
        "total": len(scatter_rows),
        "ok_ratio": ok_n / len(scatter_rows) if scatter_rows else 0,
        "per_family": {
            r["family_id"]: {
                "status": r["san_status"],
                "uroko_rel": r["uroko_rel"],
                "uroko_px": r["uroko_px"],
                "reason": r["san_reason"],
            }
            for r in scatter_rows
        },
        "verdict": (
            f"書体別チューニングなしで {ok_n}/{len(scatter_rows)} 書体が ok"
        ),
    }

    # scatter
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    xs, ys_v, labels = [], [], []
    for r in scatter_rows:
        if r["contrast"] is None or r["uroko_rel"] is None:
            continue
        xs.append(r["contrast"])
        ys_v.append(r["uroko_rel"])
        labels.append(r["label"])
        ax.scatter(r["contrast"], r["uroko_rel"], s=80, zorder=3)
        ax.annotate(
            r["label"],
            (r["contrast"], r["uroko_rel"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=9,
        )
    ax.set_xlabel("contrast (vert / horiz) — juu_contrast")
    ax.set_ylabel("uroko relative size (protrusion / stroke) — san_uroko")
    ax.set_title("fontdb spike4: contrast × uroko  (profile=ft_1024_nohint_gray_v1)")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="#888", lw=0.5)
    scatter_path = OUT / "scatter_contrast_uroko.png"
    fig.tight_layout()
    fig.savefig(scatter_path, dpi=150)
    plt.close(fig)
    report["scatter_png"] = str(scatter_path)

    # meaningful separation?
    if len(xs) >= 2:
        c_span = max(xs) - min(xs)
        u_span = max(ys_v) - min(ys_v)
        report["scatter_separation"] = {
            "contrast_span": c_span,
            "uroko_span": u_span,
            "meaningful": bool(c_span >= 0.15 or u_span >= 0.15),
            "note": "contrast_span>=0.15 or uroko_span>=0.15 なら書体間差ありと判定",
        }
    else:
        report["scatter_separation"] = {"meaningful": False, "note": "insufficient points"}

    out_json = OUT / "mvp_report.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\nwrote", out_json)
    print("scatter", scatter_path)
    print("DB", DB)
    print("san_uroko:", report["san_uroko_stability"]["verdict"])
    conn.close()
    return report


if __name__ == "__main__":
    run()
