#!/usr/bin/env python3
"""P5 前提検証: 画数 vs 黒み密度・平均線幅（Noto Serif JP wght=400）。"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Tuple

import freetype
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

SPIKE5 = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SPIKE5, "output")
FONT = os.path.join(
    os.path.dirname(SPIKE5), "spike", "fonts", "NotoSerifJP-Regular-wght400.ttf"
)
EM_PX = 1024
THRESH = 128

# 画数既知の漢字 ≈30字（1〜29画をカバー）
CHARS: List[Tuple[str, int]] = [
    ("一", 1),
    ("乙", 1),
    ("二", 2),
    ("十", 2),
    ("人", 2),
    ("口", 3),
    ("三", 3),
    ("土", 3),
    ("日", 4),
    ("木", 4),
    ("月", 4),
    ("田", 5),
    ("目", 5),
    ("永", 5),
    ("本", 5),
    ("字", 6),
    ("年", 6),
    ("東", 8),
    ("国", 8),
    ("明", 8),
    ("書", 10),
    ("時", 10),
    ("語", 14),
    ("質", 15),
    ("論", 15),
    ("講", 17),
    ("職", 18),
    ("議", 20),
    ("競", 20),
    ("鑑", 23),
    ("鬱", 29),
]


def load_face(path: str) -> freetype.Face:
    if not os.path.isfile(path) or os.path.getsize(path) < 1000:
        raise FileNotFoundError(f"font missing: {path}")
    face = freetype.Face(path)
    face.set_pixel_sizes(EM_PX, EM_PX)
    return face


def render_glyph_gray(face: freetype.Face, char: str) -> Tuple[np.ndarray, dict]:
    flags = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER
    face.load_char(char, flags)
    glyph = face.glyph
    bitmap = glyph.bitmap
    w, h, pitch = bitmap.width, bitmap.rows, bitmap.pitch
    buf = bytes(bitmap.buffer)
    meta = {
        "width": w,
        "rows": h,
        "left": glyph.bitmap_left,
        "top": glyph.bitmap_top,
        "advance_x": glyph.advance.x / 64.0,
    }
    if w == 0 or h == 0:
        return np.zeros((0, 0), dtype=np.uint8), meta
    arr = np.zeros((h, w), dtype=np.uint8)
    for row in range(h):
        start = row * pitch
        row_bytes = buf[start : start + w] if pitch >= w else buf[start : start + max(0, pitch)].ljust(w, b"\x00")[:w]
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


def black_runs_1d(binary_line: np.ndarray) -> List[int]:
    runs: List[int] = []
    cur = 0
    for v in binary_line:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


def measure_glyph(canvas: np.ndarray) -> dict:
    bin_img = canvas >= THRESH
    ys, xs = np.where(bin_img)
    if len(xs) == 0:
        return {"status": "fail", "reason": "empty"}

    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    face_w = x_max - x_min + 1
    face_h = y_max - y_min + 1
    bbox_area = face_w * face_h
    ink = int(bin_img[y_min : y_max + 1, x_min : x_max + 1].sum())
    ink_density = ink / bbox_area if bbox_area else 0.0

    # 水平走査の黒ラン（字面内）。短〜中ラン＝縦画横断の線幅代理
    max_stroke = max(4, int(min(face_w, face_h) * 0.40))
    h_runs: List[int] = []
    for y in range(y_min, y_max + 1):
        for r in black_runs_1d(bin_img[y, x_min : x_max + 1]):
            if 2 <= r <= max_stroke:
                h_runs.append(r)

    # 垂直走査の黒ラン＝横画横断の線幅代理
    v_runs: List[int] = []
    for x in range(x_min, x_max + 1):
        for r in black_runs_1d(bin_img[y_min : y_max + 1, x]):
            if 2 <= r <= max_stroke:
                v_runs.append(r)

    med_h = float(np.median(h_runs)) if h_runs else float("nan")
    med_v = float(np.median(v_runs)) if v_runs else float("nan")
    # 平均線幅代理: 縦画系（水平走査中央値）と横画系（垂直走査中央値）の幾何平均
    if np.isfinite(med_h) and np.isfinite(med_v) and med_h > 0 and med_v > 0:
        stroke_w = float(np.sqrt(med_h * med_v))
    elif np.isfinite(med_h):
        stroke_w = med_h
    elif np.isfinite(med_v):
        stroke_w = med_v
    else:
        stroke_w = float("nan")

    # ink面積 / 推定総画長（推定画長 = ink / 線幅代理）
    est_stroke_len = (ink / stroke_w) if (np.isfinite(stroke_w) and stroke_w > 0) else float("nan")
    # 線幅代理2: ink / 推定総画長 は tautology なので、別指標として
    # 「画数あたり ink」ではなく、上記 stroke_w を主指標とする。
    # 参考: ink / stroke_count（画あたりのインク）も記録
    return {
        "status": "ok",
        "bbox": [x_min, y_min, x_max, y_max],
        "face_w": face_w,
        "face_h": face_h,
        "bbox_area": bbox_area,
        "ink_px": ink,
        "ink_density": ink_density,
        "median_h_run_px": med_h,
        "median_v_run_px": med_v,
        "stroke_width_proxy_px": stroke_w,
        "stroke_width_proxy_em": stroke_w / EM_PX if np.isfinite(stroke_w) else float("nan"),
        "est_stroke_len_px": est_stroke_len,
        "n_h_runs": len(h_runs),
        "n_v_runs": len(v_runs),
    }


def fit_power_law(strokes: np.ndarray, widths: np.ndarray) -> dict:
    """線幅 ∝ 画数^(-α) の α を log-log 最小二乗で概算。"""
    mask = (strokes > 0) & np.isfinite(widths) & (widths > 0)
    x = strokes[mask].astype(float)
    y = widths[mask].astype(float)
    if len(x) < 3:
        return {"ok": False, "reason": "insufficient points"}
    lx, ly = np.log(x), np.log(y)
    # ly = c + slope * lx ; slope = -α
    slope, intercept = np.polyfit(lx, ly, 1)
    alpha = float(-slope)
    y_hat = np.exp(intercept + slope * lx)
    ss_res = float(np.sum((y - np.exp(intercept + slope * np.log(x))) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    # Pearson on log-log
    r = float(np.corrcoef(lx, ly)[0, 1])
    return {
        "ok": True,
        "alpha": alpha,
        "intercept_log": float(intercept),
        "c": float(np.exp(intercept)),  # width ≈ c * strokes^(-α)
        "r_loglog": r,
        "r2": r2,
        "n": int(len(x)),
        "formula": f"stroke_width ≈ {np.exp(intercept):.3f} * strokes^(-{alpha:.3f})",
    }


def fit_linear(strokes: np.ndarray, values: np.ndarray) -> dict:
    mask = np.isfinite(values)
    x = strokes[mask].astype(float)
    y = values[mask].astype(float)
    if len(x) < 3:
        return {"ok": False}
    slope, intercept = np.polyfit(x, y, 1)
    y_hat = intercept + slope * x
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    r = float(np.corrcoef(x, y)[0, 1])
    return {
        "ok": True,
        "slope": float(slope),
        "intercept": float(intercept),
        "r": r,
        "r2": r2,
        "n": int(len(x)),
    }


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    face = load_face(FONT)
    family = face.family_name.decode() if isinstance(face.family_name, bytes) else str(face.family_name)
    style = face.style_name.decode() if isinstance(face.style_name, bytes) else str(face.style_name)

    rows = []
    for ch, strokes in CHARS:
        gray, meta = render_glyph_gray(face, ch)
        canvas = place_on_em_canvas(gray, meta)
        m = measure_glyph(canvas)
        # サンプル PNG（代表字のみ）
        if ch in ("一", "十", "国", "議", "鬱"):
            Image.fromarray(canvas, mode="L").save(
                os.path.join(OUT, f"sample_{ord(ch):04x}_{ch}.png")
            )
        row = {
            "char": ch,
            "unicode": f"U+{ord(ch):04X}",
            "strokes": strokes,
            **m,
        }
        rows.append(row)
        print(
            f"{ch} strokes={strokes:2d} density={m.get('ink_density', float('nan')):.4f} "
            f"w={m.get('stroke_width_proxy_px', float('nan')):.1f}px"
        )

    strokes_arr = np.array([r["strokes"] for r in rows], dtype=float)
    dens_arr = np.array([r["ink_density"] for r in rows], dtype=float)
    width_arr = np.array([r["stroke_width_proxy_px"] for r in rows], dtype=float)
    ink_per_stroke = np.array(
        [r["ink_px"] / r["strokes"] for r in rows], dtype=float
    )

    fit_w = fit_power_law(strokes_arr, width_arr)
    fit_d = fit_linear(strokes_arr, dens_arr)
    fit_ips = fit_power_law(strokes_arr, ink_per_stroke)

    # --- plots ---
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    ax = axes[0]
    ax.scatter(strokes_arr, dens_arr, c="#1a1a1a", s=36, zorder=3)
    for r in rows:
        ax.annotate(
            r["char"],
            (r["strokes"], r["ink_density"]),
            textcoords="offset points",
            xytext=(3, 3),
            fontsize=7,
            alpha=0.85,
        )
    if fit_d.get("ok"):
        xs = np.linspace(strokes_arr.min(), strokes_arr.max(), 50)
        ax.plot(xs, fit_d["intercept"] + fit_d["slope"] * xs, color="#c45c26", lw=1.5,
                label=f"linear slope={fit_d['slope']:.4f}, r={fit_d['r']:.3f}")
        ax.legend(fontsize=8)
    ax.set_xlabel("stroke count")
    ax.set_ylabel("ink density (ink / glyph bbox)")
    ax.set_title("(a) strokes vs ink density")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.scatter(strokes_arr, width_arr, c="#1a1a1a", s=36, zorder=3)
    for r in rows:
        ax.annotate(
            r["char"],
            (r["strokes"], r["stroke_width_proxy_px"]),
            textcoords="offset points",
            xytext=(3, 3),
            fontsize=7,
            alpha=0.85,
        )
    if fit_w.get("ok"):
        xs = np.linspace(max(1, strokes_arr.min()), strokes_arr.max(), 80)
        ys = fit_w["c"] * xs ** (-fit_w["alpha"])
        ax.plot(
            xs,
            ys,
            color="#c45c26",
            lw=1.5,
            label=f"w ∝ n^(-α), α={fit_w['alpha']:.3f}, r={fit_w['r_loglog']:.3f}",
        )
        ax.legend(fontsize=8)
    ax.set_xlabel("stroke count")
    ax.set_ylabel("stroke width proxy (px @1024/EM)")
    ax.set_title("(b) strokes vs stroke-width proxy")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        f"Noto Serif JP (wght=400) — blackness attenuation @ {EM_PX}px/EM",
        fontsize=11,
    )
    fig.tight_layout()
    plot_ab = os.path.join(OUT, "strokes_vs_density_width.png")
    fig.savefig(plot_ab, dpi=150)
    plt.close(fig)

    # log-log plot for width
    fig2, ax = plt.subplots(figsize=(6, 4.5))
    mask = np.isfinite(width_arr) & (width_arr > 0)
    ax.scatter(strokes_arr[mask], width_arr[mask], c="#1a1a1a", s=36, zorder=3)
    if fit_w.get("ok"):
        xs = np.logspace(np.log10(max(1, strokes_arr.min())), np.log10(strokes_arr.max()), 80)
        ax.plot(xs, fit_w["c"] * xs ** (-fit_w["alpha"]), color="#c45c26", lw=1.5,
                label=fit_w["formula"])
        ax.legend(fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("stroke count (log)")
    ax.set_ylabel("stroke width proxy (log px)")
    ax.set_title("log-log: stroke width ∝ strokes^(-α)")
    ax.grid(True, which="both", alpha=0.3)
    fig2.tight_layout()
    plot_log = os.path.join(OUT, "strokes_vs_width_loglog.png")
    fig2.savefig(plot_log, dpi=150)
    plt.close(fig2)

    # ink per stroke plot
    fig3, ax = plt.subplots(figsize=(6, 4.5))
    ax.scatter(strokes_arr, ink_per_stroke, c="#1a1a1a", s=36, zorder=3)
    for r, ips in zip(rows, ink_per_stroke):
        ax.annotate(r["char"], (r["strokes"], ips), textcoords="offset points",
                    xytext=(3, 3), fontsize=7, alpha=0.85)
    if fit_ips.get("ok"):
        xs = np.linspace(max(1, strokes_arr.min()), strokes_arr.max(), 80)
        ax.plot(xs, fit_ips["c"] * xs ** (-fit_ips["alpha"]), color="#c45c26", lw=1.5,
                label=f"ink/stroke ∝ n^(-α), α={fit_ips['alpha']:.3f}")
        ax.legend(fontsize=8)
    ax.set_xlabel("stroke count")
    ax.set_ylabel("ink px / stroke count")
    ax.set_title("strokes vs ink-per-stroke (supplementary)")
    ax.grid(True, alpha=0.3)
    fig3.tight_layout()
    plot_ips = os.path.join(OUT, "strokes_vs_ink_per_stroke.png")
    fig3.savefig(plot_ips, dpi=150)
    plt.close(fig3)

    # 判定
    # 減衰カーブ観測: α>0 かつ log-log 相関が負で |r| がある程度大きい
    observed = bool(
        fit_w.get("ok")
        and fit_w["alpha"] > 0.05
        and fit_w["r_loglog"] < -0.35
    )
    # 密度が画数と強く正相関なら減衰不足、弱/負なら減衰が効いている
    density_rising = bool(fit_d.get("ok") and fit_d["r"] > 0.5)

    if observed and not density_rising:
        verdict = "観測できた（減衰カーブあり。密度は画数に強く連動せず、線幅が画数で減衰）"
    elif observed and density_rising:
        verdict = "部分的に観測（線幅は減衰するが、密度も画数とともに上昇＝減衰が不完全）"
    else:
        verdict = "観測できなかった（線幅の画数減衰が弱い／不明瞭。P5前提の修正が必要）"

    report = {
        "font_path": FONT,
        "family": family,
        "style": style,
        "protocol": {
            "em_px": EM_PX,
            "threshold": THRESH,
            "load_flags": "FT_LOAD_NO_HINTING | FT_LOAD_RENDER",
            "ink_density": "black_pixels / glyph_bbox_area",
            "stroke_width_proxy": "sqrt(median_h_run * median_v_run); runs filtered 2..0.4*min(face)",
        },
        "n_chars": len(rows),
        "rows": rows,
        "fit_stroke_width_powerlaw": fit_w,
        "fit_density_linear": fit_d,
        "fit_ink_per_stroke_powerlaw": fit_ips,
        "plots": {
            "ab": plot_ab,
            "loglog": plot_log,
            "ink_per_stroke": plot_ips,
        },
        "verdict": {
            "attenuation_observed": observed,
            "density_rises_with_strokes": density_rising,
            "alpha": fit_w.get("alpha"),
            "summary": verdict,
        },
    }

    out_json = os.path.join(OUT, "density_curve_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=True)

    # CSV table
    csv_path = os.path.join(OUT, "density_curve_table.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(
            "char,unicode,strokes,ink_density,stroke_width_proxy_px,"
            "median_h_run_px,median_v_run_px,ink_px,bbox_area\n"
        )
        for r in rows:
            f.write(
                f"{r['char']},{r['unicode']},{r['strokes']},"
                f"{r['ink_density']:.6f},{r['stroke_width_proxy_px']:.3f},"
                f"{r['median_h_run_px']:.3f},{r['median_v_run_px']:.3f},"
                f"{r['ink_px']},{r['bbox_area']}\n"
            )

    print("VERDICT:", verdict)
    print("alpha:", fit_w.get("alpha"))
    print("wrote", out_json)
    print("plots:", plot_ab, plot_log, plot_ips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
