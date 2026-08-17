#!/usr/bin/env python3
"""exact 輪郭からステムと端物を分ける。正本は書かない。

知見: 寸分違わぬは輪郭そのもの。要素はそこから切る。組み直して xor 面積が 0 なら抽出はロスレス。

例:
  engine/.venv/bin/python scripts/extract_ref_elements.py --chars 十ニ三口日
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from pathops import Path, difference, intersection, union, xor
from fontTools.pens.recordingPen import DecomposingRecordingPen, replayRecording
from fontTools.ttLib import TTFont

from reproduce_ref import REF_DEFAULT, OUT_DEFAULT, assert_throwaway

QUAD_STEPS = 8
ANGLE_TOL = math.radians(10)
MIN_THICK_FRAC = 0.008
MAX_THICK_FRAC = 0.14
MIN_LEN_FRAC = 0.18
# 穴の上下辺は平行で max_thick 以内に入る。インクが薄い矩形はステムではない。
STEM_INK_MIN = 0.55


def glyph_recording(ref: Path, ch: str):
    tt = TTFont(ref)
    cmap = tt.getBestCmap() or {}
    code = ord(ch)
    if code not in cmap:
        raise KeyError(f"{ch} not in {ref}")
    gs = tt.getGlyphSet()
    rec = DecomposingRecordingPen(gs)
    gs[cmap[code]].draw(rec)
    return rec.value, gs[cmap[code]].width, int(tt["head"].unitsPerEm), cmap[code]


def recording_to_path(rec) -> Path:
    p = Path()
    replayRecording(rec, p.getPen())
    return p


def _quad(p0, c, p1, steps: int) -> list[tuple[float, float]]:
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
            )
        )
    return out


def flatten(rec) -> list[list[tuple[float, float]]]:
    contours: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    last = None
    for op, args in rec:
        if op == "moveTo":
            if cur:
                contours.append(cur)
            last = (float(args[0][0]), float(args[0][1]))
            cur = [last]
        elif op == "lineTo":
            last = (float(args[0][0]), float(args[0][1]))
            cur.append(last)
        elif op == "qCurveTo":
            pts = [(float(p[0]), float(p[1])) for p in args]
            on = pts[-1]
            start = last
            if start is None:
                continue
            if len(pts) == 2:
                cur.extend(_quad(start, pts[0], on, QUAD_STEPS))
            else:
                prev = start
                offs = pts[:-1]
                for i, off in enumerate(offs):
                    end = on if i == len(offs) - 1 else (
                        (off[0] + offs[i + 1][0]) / 2,
                        (off[1] + offs[i + 1][1]) / 2,
                    )
                    cur.extend(_quad(prev, off, end, QUAD_STEPS))
                    prev = end
            last = on
        elif op == "curveTo":
            last = (float(args[-1][0]), float(args[-1][1]))
            cur.append(last)
        elif op == "closePath":
            if cur:
                contours.append(cur)
            cur = []
            last = None
    if cur:
        contours.append(cur)
    return contours


def _edges(contours):
    hs = []
    vs = []
    for pts in contours:
        if len(pts) < 2:
            continue
        ring = pts + [pts[0]]
        for a, b in zip(ring, ring[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1:
                continue
            ang = abs(math.atan2(dy, dx))
            if min(ang, abs(ang - math.pi)) <= ANGLE_TOL:
                y = 0.5 * (a[1] + b[1])
                x0, x1 = sorted((a[0], b[0]))
                hs.append((y, x0, x1, length))
            if abs(ang - math.pi / 2) <= ANGLE_TOL:
                x = 0.5 * (a[0] + b[0])
                y0, y1 = sorted((a[1], b[1]))
                vs.append((x, y0, y1, length))
    return hs, vs


def _pair_slabs(edges, *, vertical: bool, min_thick: float, max_thick: float, min_len: float):
    """平行エッジを太さで組んで矩形にする。"""
    edges = sorted(edges, key=lambda e: e[0])
    rects = []
    for i, a in enumerate(edges):
        for b in edges[i + 1 :]:
            gap = b[0] - a[0]
            if gap < min_thick:
                continue
            if gap > max_thick:
                break
            lo = max(a[1], b[1])
            hi = min(a[2], b[2])
            span = hi - lo
            if span < min_len:
                continue
            if vertical:
                rects.append((a[0], lo, b[0], hi, gap, span, "v"))
            else:
                rects.append((lo, a[0], hi, b[0], gap, span, "h"))
    return rects


def _ink_frac(exact: Path, x0: float, y0: float, x1: float, y1: float) -> float:
    r = rect_path(x0, y0, x1, y1)
    inter = Path()
    intersection([exact], [r], inter.getPen(), fix_winding=True)
    area = abs((x1 - x0) * (y1 - y0)) or 1.0
    return abs(inter.area) / area


def filter_ink_stems(exact: Path, rects: list[tuple]) -> list[tuple]:
    return [r for r in rects if _ink_frac(exact, r[0], r[1], r[2], r[3]) >= STEM_INK_MIN]


def _dedupe_rects(rects: list[tuple]) -> list[tuple]:
    kept: list[tuple] = []
    for r in sorted(rects, key=lambda t: t[5], reverse=True):
        x0, y0, x1, y1 = r[0], r[1], r[2], r[3]
        area = max(1.0, (x1 - x0) * (y1 - y0))
        drop = False
        for k in kept:
            ix0, iy0, ix1, iy1 = max(x0, k[0]), max(y0, k[1]), min(x1, k[2]), min(y1, k[3])
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            if inter / area > 0.65:
                drop = True
                break
        if not drop:
            kept.append(r)
    return kept


def rect_path(x0, y0, x1, y1) -> Path:
    p = Path()
    pen = p.getPen()
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return p


def combine(paths: list[Path], op) -> Path:
    out = Path()
    if not paths:
        return out
    if len(paths) == 1:
        return paths[0]
    op(paths, out.getPen(), fix_winding=True)
    return out


def residual_contours(path: Path) -> list[dict]:
    items = []
    for c in path.contours:
        b = c.bounds
        items.append(
            {
                "bounds": [round(v, 2) for v in b] if b else None,
                "area": round(abs(c.area), 1),
                "clockwise": bool(c.clockwise),
            }
        )
    return items


def _nearest_stem(bounds, stems: list[dict], kind: str | None = None) -> dict | None:
    if not bounds:
        return None
    cx, cy = 0.5 * (bounds[0] + bounds[2]), 0.5 * (bounds[1] + bounds[3])
    best = None
    best_d = 1e18
    for s in stems:
        if kind and s["kind"] != kind:
            continue
        dx = max(s["x0"] - cx, 0.0, cx - s["x1"])
        dy = max(s["y0"] - cy, 0.0, cy - s["y1"])
        d = dx * dx + dy * dy
        if d < best_d:
            best, best_d = s, d
    return best


def extract_counters(exact: Path, upm: float) -> list[dict]:
    items = []
    for c in exact.contours:
        if c.clockwise:
            continue
        b = c.bounds
        items.append(
            {
                "bounds_em": [round(v / upm, 4) for v in b],
                "area_em": round(abs(c.area) / (upm * upm), 5),
            }
        )
    return items


def classify_role(item: dict, row: dict) -> str:
    b = item.get("bounds")
    if not b:
        return "other"
    x0, y0, x1, y1 = b
    w, h = x1 - x0, y1 - y0
    area = item["area"]
    ht = row["h_thickness"] or 50.0
    vt = row["v_thickness"] or ht * 2.5
    face = row["face"]
    fw = max(1.0, face[2] - face[0])
    fh = max(1.0, face[3] - face[1])
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    rel_x = (cx - face[0]) / fw
    rel_y = (cy - face[1]) / fh
    exact = row["exact_area"] or 1.0
    if w <= vt * 1.15 and h <= ht * 1.15:
        return "junction"
    if area > 0.65 * exact and w > 0.7 * fw and h > 0.7 * fh:
        return "hara_pair"
    if w > 0.75 * fw and h > 0.35 * fh and area > 0.25 * exact:
        return "hara_pair"
    if area > 0.12 * exact and h > 0.45 * fh:
        return "right_hara" if rel_x >= 0.5 else "left_hara"
    hs = [s for s in row["stems"] if s["kind"] == "h"]
    vs = [s for s in row["stems"] if s["kind"] == "v"]
    touches_h_end = any(
        abs(s["x1"] - x0) <= vt and abs(s["y1"] - y0) <= ht * 3 for s in hs
    )
    touches_v_top = any(
        abs(s["y1"] - y0) <= ht * 2.5 and s["x0"] - 20 <= cx <= s["x1"] + 80 for s in vs
    )
    if touches_h_end and touches_v_top:
        fit = uroko_scalars(item, row["stems"], 1.0)
        hon = fit["height_over_h"] if fit else h / ht
        return "box_uroko" if hon < 3.3 else "bar_uroko"
    if touches_v_top and not touches_h_end and h < 0.22 * fh:
        return "top_cap"
    if rel_y > 0.78 and 0.02 * exact < area < 0.18 * exact and h < 0.28 * fh:
        attached = False
        for s in hs:
            if abs(s["y0"] - y0) <= ht * 2.5 and abs(s["x1"] - x0) <= vt * 1.2:
                attached = True
                break
        if not attached:
            return "ten"
    if hs:
        right = max(s["x1"] for s in hs)
        left = min(s["x0"] for s in hs)
        if cx > right - 0.12 * fw and h > ht * 1.6 and w > ht * 2.0:
            near_h = any(abs(0.5 * (s["y0"] + s["y1"]) - cy) < 0.2 * fh for s in hs)
            if near_h:
                fit = uroko_scalars(item, row["stems"], 1.0)
                hon = fit["height_over_h"] if fit else h / ht
                return "box_uroko" if hon < 3.3 else "bar_uroko"
        if cx < left + 0.12 * fw and w < vt * 1.4:
            return "uchikomi"
    if vs:
        top = max(s["y1"] for s in vs)
        bot = min(s["y0"] for s in vs)
        if cy > top - 0.12 * fh and h < 0.2 * fh:
            return "top_cap"
        if cy < bot + 0.2 * fh and area < 0.15 * exact and w > vt * 0.8:
            return "hane"
        if cy < bot + 0.15 * fh and area < 0.08 * exact:
            return "tome"
    return "other"


def uroko_scalars(item: dict, stems: list[dict], upm: float) -> dict | None:
    b = item.get("bounds")
    stem = _nearest_stem(b, stems, "h")
    if not b or stem is None:
        return None
    w = b[2] - stem["x1"]
    h = b[3] - stem["y0"]
    th = stem["thickness"] or 1.0
    if w < 20 or h < th * 1.5:
        return None
    return {
        "width_over_h": round(w / th, 2),
        "height_over_h": round(h / th, 2),
        "width_em": round(w / upm, 4),
        "height_em": round(h / upm, 4),
    }


def classify_terminal(bounds, stems: list[dict]) -> str:
    if not bounds:
        return "other"
    x0, y0, x1, y1 = bounds
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    hs = [s for s in stems if s["kind"] == "h"]
    vs = [s for s in stems if s["kind"] == "v"]
    if hs:
        right = max(s["x1"] for s in hs)
        left = min(s["x0"] for s in hs)
        if cx > right - 0.15 * (right - left):
            return "uroko"
        if cx < left + 0.15 * (right - left):
            return "uchikomi"
    if vs:
        top = max(s["y1"] for s in vs)
        if cy > top - 0.2 * max(s["y1"] - s["y0"] for s in vs):
            return "top_cap"
    return "other"


def extract_char(ref: Path, ch: str) -> dict:
    rec, width, upm, src_name = glyph_recording(ref, ch)
    exact = recording_to_path(rec)
    bounds = exact.bounds
    face_w = bounds[2] - bounds[0]
    face_h = bounds[3] - bounds[1]
    min_thick = MIN_THICK_FRAC * upm
    max_thick = MAX_THICK_FRAC * upm
    min_len = MIN_LEN_FRAC * max(face_w, face_h)
    hs, vs = _edges(flatten(rec))
    # 先にインク濾過。穴矩形を残すと細い本物が重複削除で消える。
    h_rects = _dedupe_rects(
        filter_ink_stems(
            exact,
            _pair_slabs(hs, vertical=False, min_thick=min_thick, max_thick=max_thick, min_len=min_len),
        )
    )
    v_rects = _dedupe_rects(
        filter_ink_stems(
            exact,
            _pair_slabs(vs, vertical=True, min_thick=min_thick, max_thick=max_thick, min_len=min_len * 0.6),
        )
    )
    stems = []
    stem_paths = []
    for x0, y0, x1, y1, thick, length, kind in h_rects + v_rects:
        stems.append(
            {
                "kind": kind,
                "x0": round(x0, 2),
                "y0": round(y0, 2),
                "x1": round(x1, 2),
                "y1": round(y1, 2),
                "thickness": round(thick, 2),
                "length": round(length, 2),
            }
        )
        stem_paths.append(rect_path(x0, y0, x1, y1))
    stems_u = combine(stem_paths, union) if stem_paths else Path()
    residual = Path()
    if stem_paths:
        difference([exact], [stems_u], residual.getPen(), fix_winding=True)
    else:
        residual = exact
    rebuilt = Path()
    if stem_paths:
        union([stems_u, residual], rebuilt.getPen(), fix_winding=True)
    else:
        rebuilt = exact
    err = Path()
    xor([exact], [rebuilt], err.getPen(), fix_winding=True)
    xor_area = abs(err.area)
    exact_area = abs(exact.area) or 1.0
    h_th = [s["thickness"] for s in stems if s["kind"] == "h"]
    v_th = [s["thickness"] for s in stems if s["kind"] == "v"]
    h_med = float(sorted(h_th)[len(h_th) // 2]) if h_th else None
    v_med = float(sorted(v_th)[len(v_th) // 2]) if v_th else None
    lsb = bounds[0]
    rsb = width - bounds[2]
    face = [round(v, 2) for v in bounds]
    partial = {
        "stems": stems,
        "h_thickness": h_med,
        "v_thickness": v_med,
        "face": face,
        "exact_area": exact_area,
    }
    terminals = []
    for item in residual_contours(residual):
        item["kind"] = classify_terminal(item["bounds"], stems)
        item["role"] = classify_role(item, partial)
        if item["role"] in ("bar_uroko", "box_uroko"):
            fit = uroko_scalars(item, stems, upm)
            if fit:
                item["uroko"] = fit
        terminals.append(item)
    counters = extract_counters(exact, upm)
    n_outer = sum(1 for c in exact.contours if c.clockwise)
    return {
        "char": ch,
        "src_name": src_name,
        "unicode": f"U+{ord(ch):04X}",
        "upm": upm,
        "width": width,
        "lsb": round(lsb, 2),
        "rsb": round(rsb, 2),
        "lsb_em": round(lsb / upm, 4),
        "rsb_em": round(rsb / upm, 4),
        "face": face,
        "face_em": [round((face[2] - face[0]) / upm, 4), round((face[3] - face[1]) / upm, 4)],
        "ink_em": round(exact_area / (upm * upm), 4),
        "exact_area": round(exact_area, 1),
        "stems": stems,
        "h_thickness": h_med,
        "v_thickness": v_med,
        "h_thickness_em": round(h_med / upm, 4) if h_med else None,
        "v_thickness_em": round(v_med / upm, 4) if v_med else None,
        "contrast_v_over_h": round(v_med / h_med, 3) if h_med and v_med else None,
        "terminals": terminals,
        "roles": sorted({t["role"] for t in terminals}),
        "counters": counters,
        "n_counter": len(counters),
        "n_outer": n_outer,
        "xor_area": round(xor_area, 2),
        "lossless": xor_area <= 1.0,
        "residual_frac": round(sum(t["area"] for t in terminals) / exact_area, 3),
    }


def sheet(rows: list[dict], dest: Path) -> None:
    lines = [
        "# 参照要素抽出",
        "",
        "exact 輪郭をステム矩形と端物残差に分ける。xor 面積 0 がロスレス。正本は書いていない。",
        "",
        "| 字 | 横em | 縦em | contrast | 穴 | roles | residual | lossless |",
        "|---|---:|---:|---:|---:|---|---:|---|",
    ]
    for r in rows:
        roles = ",".join(r.get("roles") or []) or "—"
        lines.append(
            f"| {r['char']} | {r.get('h_thickness_em') or '—'} | {r.get('v_thickness_em') or '—'} | "
            f"{r['contrast_v_over_h'] or '—'} | {r.get('n_counter', 0)} | {roles} | "
            f"{r['residual_frac']} | {'yes' if r['lossless'] else 'NO'} |"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract stems and terminals from exact outlines")
    ap.add_argument("--ref", type=Path, default=REF_DEFAULT)
    ap.add_argument("--chars", default="十ニ三口日")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if not args.ref.is_file():
        print(f"error: missing {args.ref}", file=sys.stderr)
        return 2
    assert_throwaway(args.out / "_scratch")
    rows = [extract_char(args.ref, ch) for ch in args.chars]
    payload = {
        "ref": str(args.ref),
        "shipping_ufo_written": False,
        "method": "exact-outline-split",
        "glyphs": rows,
        "all_lossless": all(r["lossless"] for r in rows),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "elements.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = args.out / "elements.md"
    sheet(rows, md_path)
    for r in rows:
        print(
            f"{r['char']} stems={len(r['stems'])} h={r['h_thickness']} v={r['v_thickness']} "
            f"c={r['contrast_v_over_h']} term={len(r['terminals'])} "
            f"xor={r['xor_area']} lossless={r['lossless']}"
        )
    print(f"wrote {json_path} {md_path}")
    return 0 if payload["all_lossless"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
