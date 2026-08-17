#!/usr/bin/env python3
"""参照書体を捨てUFO経由で焼き直す。正本は書かない。

--mode exact: 輪郭をソース UPM のまま通す（寸分違わぬ）。
--mode invert: ラスタ骨格＋幅の近似（実験用）。

例:
  engine/.venv/bin/python scripts/reproduce_ref.py --mode exact --chars 十ニ三口日
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SHIP_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
REF_DEFAULT = ROOT / "fontdb/data/fonts/ipaex_mincho-Regular.ttf"
OUT_DEFAULT = ROOT / "proofs" / "reproduce"
SCRATCH = OUT_DEFAULT / "_scratch"
EM_PX = 256
INK = 64
UPM = 1000
WIDTH = 1000

sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "fontdb" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def assert_throwaway(dest: Path) -> Path:
    dest = dest.resolve()
    ship = SHIP_UFO.resolve()
    if dest == ship or ship in dest.parents or dest in ship.parents:
        raise ValueError(f"refuse shipping UFO: {dest}")
    return dest


def render_em(font: Path, char: str, em_px: int = EM_PX) -> np.ndarray:
    import freetype

    face = freetype.Face(str(font))
    face.set_pixel_sizes(em_px, em_px)
    face.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bm = face.glyph.bitmap
    glyph = np.zeros((bm.rows, bm.width), dtype=np.uint8)
    buf = bytes(bm.buffer)
    for r in range(bm.rows):
        glyph[r, :] = np.frombuffer(buf[r * bm.pitch : r * bm.pitch + bm.width], dtype=np.uint8)
    canvas = np.zeros((em_px, em_px), dtype=np.uint8)
    if glyph.size == 0:
        return canvas
    baseline = int(em_px * 0.88)
    x0 = (em_px - int(face.glyph.advance.x / 64.0)) // 2 + face.glyph.bitmap_left
    y0 = baseline - face.glyph.bitmap_top
    h, w = glyph.shape
    x1, y1 = x0 + w, y0 + h
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(em_px, x1), min(em_px, y1)
    if cx0 < cx1 and cy0 < cy1:
        canvas[cy0:cy1, cx0:cx1] = np.maximum(
            canvas[cy0:cy1, cx0:cx1],
            glyph[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0],
        )
    return canvas


def longest_run(row: np.ndarray) -> int:
    best = cur = 0
    for v in row:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def extract_stems(canvas: np.ndarray, threshold: int = INK) -> dict:
    from fontdb.probes.juu_contrast import measure_juu_contrast

    return measure_juu_contrast(canvas, threshold=threshold, em_px=canvas.shape[0])


def zhang_suen(binary: np.ndarray) -> np.ndarray:
    """2値画像を骨格化する。入力は True=インク。"""
    img = binary.astype(np.uint8)
    h, w = img.shape
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            to_clear: list[tuple[int, int]] = []
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if img[y, x] == 0:
                        continue
                    p2, p3, p4 = img[y - 1, x], img[y - 1, x + 1], img[y, x + 1]
                    p5, p6, p7 = img[y + 1, x + 1], img[y + 1, x], img[y + 1, x - 1]
                    p8, p9 = img[y, x - 1], img[y - 1, x - 1]
                    neigh = [p2, p3, p4, p5, p6, p7, p8, p9]
                    b = int(sum(neigh))
                    if b < 2 or b > 6:
                        continue
                    a = 0
                    cycle = neigh + [neigh[0]]
                    for i in range(8):
                        if cycle[i] == 0 and cycle[i + 1] == 1:
                            a += 1
                    if a != 1:
                        continue
                    if step == 0:
                        if p2 * p4 * p6 != 0 or p4 * p6 * p8 != 0:
                            continue
                    else:
                        if p2 * p4 * p8 != 0 or p2 * p6 * p8 != 0:
                            continue
                    to_clear.append((y, x))
            if to_clear:
                changed = True
                for y, x in to_clear:
                    img[y, x] = 0
    return img.astype(bool)


def _neighbors(skel: np.ndarray, y: int, x: int) -> list[tuple[int, int]]:
    h, w = skel.shape
    out: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and skel[yy, xx]:
                out.append((yy, xx))
    return out


def trace_polylines(skel: np.ndarray) -> list[list[tuple[int, int]]]:
    """骨格を端点から辿って折れ線にする。"""
    pts = list(zip(*np.where(skel)))
    if not pts:
        return []
    deg = {(y, x): len(_neighbors(skel, y, x)) for y, x in pts}
    unused = set(pts)
    lines: list[list[tuple[int, int]]] = []

    def walk(start: tuple[int, int]) -> list[tuple[int, int]]:
        path = [start]
        unused.discard(start)
        prev = None
        cur = start
        while True:
            cand = [n for n in _neighbors(skel, cur[0], cur[1]) if n in unused or n == prev]
            nxts = [n for n in _neighbors(skel, cur[0], cur[1]) if n in unused]
            if not nxts:
                break
            nxt = nxts[0]
            unused.discard(nxt)
            path.append(nxt)
            prev, cur = cur, nxt
            if deg.get(cur, 0) >= 3 and len(path) > 1:
                unused.add(cur)
                break
        return path

    ends = [p for p, d in deg.items() if d == 1]
    for e in ends:
        if e in unused:
            lines.append(walk(e))
    while unused:
        lines.append(walk(next(iter(unused))))
    return [ln for ln in lines if len(ln) >= 2]


def rdp(points: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ax, ay = b[0] - a[0], b[1] - a[1]
    lab = math.hypot(ax, ay) or 1.0
    best_i = 0
    best_d = -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i][0] - a[0], points[i][1] - a[1]
        d = abs(ax * py - ay * px) / lab
        if d > best_d:
            best_d, best_i = d, i
    if best_d <= eps:
        return [a, b]
    left = rdp(points[: best_i + 1], eps)
    right = rdp(points[best_i:], eps)
    return left[:-1] + right


def radius_at(binary: np.ndarray, y: int, x: int) -> float:
    h, w = binary.shape
    best = 64.0
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        r = 0
        yy, xx = y, x
        step = math.hypot(dy, dx)
        while True:
            yy += dy
            xx += dx
            if yy < 0 or xx < 0 or yy >= h or xx >= w or not binary[yy, xx]:
                break
            r += 1
        best = min(best, r * step)
    return max(1.0, best)


def pix_to_font(x: float, y: float, em_px: int = EM_PX) -> tuple[float, float]:
    s = UPM / em_px
    return x * s, (em_px - y) * s


def capsule(p0: tuple[float, float], p1: tuple[float, float], r0: float, r1: float) -> list[tuple[float, float]]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    a = (p0[0] + nx * r0, p0[1] + ny * r0)
    b = (p1[0] + nx * r1, p1[1] + ny * r1)
    c = (p1[0] - nx * r1, p1[1] - ny * r1)
    d = (p0[0] - nx * r0, p0[1] - ny * r0)
    return [a, b, c, d]


def rebuild_contours(canvas: np.ndarray) -> tuple[list[list[tuple[float, float]]], dict]:
    binary = canvas >= INK
    stems = extract_stems(canvas)
    ys, xs = np.where(binary)
    work = binary
    yoff = xoff = 0
    if len(xs):
        y0, y1 = max(0, int(ys.min()) - 2), min(binary.shape[0], int(ys.max()) + 3)
        x0, x1 = max(0, int(xs.min()) - 2), min(binary.shape[1], int(xs.max()) + 3)
        work = binary[y0:y1, x0:x1]
        yoff, xoff = y0, x0
    skel_local = zhang_suen(work)
    skel = np.zeros_like(binary)
    if skel_local.size:
        skel[yoff : yoff + skel_local.shape[0], xoff : xoff + skel_local.shape[1]] = skel_local
    raw_lines = trace_polylines(skel)
    contours: list[list[tuple[float, float]]] = []
    n_pts = 0
    for line in raw_lines:
        simp = rdp([(float(x), float(y)) for y, x in line], eps=1.6)
        if len(simp) < 2:
            continue
        radii = []
        for x, y in simp:
            radii.append(radius_at(binary, int(round(y)), int(round(x))) * (UPM / EM_PX))
        for i in range(len(simp) - 1):
            p0 = pix_to_font(*simp[i])
            p1 = pix_to_font(*simp[i + 1])
            contours.append(capsule(p0, p1, radii[i], radii[i + 1]))
            n_pts += 1
    feat = {
        "stems": {
            "status": stems.get("status"),
            "vert_px": stems.get("vert_thickness_px"),
            "horiz_px": stems.get("horiz_thickness_px"),
            "contrast": stems.get("contrast_v_over_h"),
        },
        "skeleton_polylines": len(raw_lines),
        "rebuild_segments": n_pts,
        "ink_px": int(binary.sum()),
    }
    return contours, feat


def subset_exact(ref: Path, chars: str, dest_ttf: Path) -> dict[str, dict]:
    """参照のグリフをサブセットして通す。座標変換も fontmake もしない。"""
    from fontTools.subset import Options, Subsetter
    from fontTools.ttLib import TTFont

    dest_ttf = assert_throwaway(dest_ttf)
    dest_ttf.parent.mkdir(parents=True, exist_ok=True)
    tt = TTFont(ref)
    cmap = tt.getBestCmap() or {}
    unicodes = []
    meta: dict[str, dict] = {}
    for ch in chars:
        code = ord(ch)
        if code not in cmap:
            raise KeyError(f"{ch} not in {ref}")
        unicodes.append(code)
        meta[ch] = {"src_name": cmap[code], "unicode": code}
    opt = Options()
    opt.glyph_names = True
    opt.legacy_kern = True
    opt.notdef_outline = True
    opt.recommended_glyphs = True
    opt.layout_features = ["*"]
    opt.name_IDs = ["*"]
    opt.name_legacy = True
    opt.name_languages = ["*"]
    subsetter = Subsetter(options=opt)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(tt)
    tt.save(dest_ttf)
    return meta


def copy_exact_glyphs(ref: Path, chars: str, dest_ufo: Path) -> dict[str, dict]:
    """参照グリフの輪郭と字幅を、UPM を変えずに捨てUFOへ通す。"""
    import shutil

    import ufoLib2
    from fontTools.pens.recordingPen import DecomposingRecordingPen, replayRecording
    from fontTools.ttLib import TTFont

    dest_ufo = assert_throwaway(dest_ufo)
    if dest_ufo.exists():
        shutil.rmtree(dest_ufo)

    tt = TTFont(ref)
    cmap = tt.getBestCmap() or {}
    gs = tt.getGlyphSet()
    upm = int(tt["head"].unitsPerEm)
    font = ufoLib2.Font()
    font.info.familyName = "MyMinchoReproduceExact"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = upm
    font.info.ascender = int(getattr(tt["hhea"], "ascent", int(upm * 0.88)))
    font.info.descender = int(getattr(tt["hhea"], "descent", -int(upm * 0.12)))
    nd = font.newGlyph(".notdef")
    nd.width = upm
    meta: dict[str, dict] = {}
    for ch in chars:
        code = ord(ch)
        if code not in cmap:
            raise KeyError(f"{ch} not in {ref}")
        src_name = cmap[code]
        rec = DecomposingRecordingPen(gs)
        gs[src_name].draw(rec)
        g = font.newGlyph(uniname(ch))
        g.unicodes = [code]
        g.width = int(round(gs[src_name].width))
        replayRecording(rec.value, g.getPen())
        meta[ch] = {
            "src_name": src_name,
            "width": g.width,
            "upm": upm,
            "verbs": [op for op, _ in rec.value],
        }
    dest_ufo.parent.mkdir(parents=True, exist_ok=True)
    font.save(dest_ufo)
    return meta


def write_ufo(path: Path, glyphs: dict[str, tuple[int, list]]) -> None:
    import ufoLib2

    if path.exists():
        import shutil

        shutil.rmtree(path)
    font = ufoLib2.Font()
    font.info.familyName = "MyMinchoReproduce"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = UPM
    font.info.ascender = 880
    font.info.descender = -120
    nd = font.newGlyph(".notdef")
    nd.width = WIDTH
    for name, (code, contours) in glyphs.items():
        g = font.newGlyph(name)
        g.width = WIDTH
        g.unicodes = [code]
        pen = g.getPen()
        for pts in contours:
            pen.moveTo(pts[0])
            for pt in pts[1:]:
                pen.lineTo(pt)
            pen.closePath()
    path.parent.mkdir(parents=True, exist_ok=True)
    font.save(path)


def pack_bbox(canvas: np.ndarray, size: int = 200) -> np.ndarray:
    from PIL import Image

    ink = canvas >= INK
    ys, xs = np.where(ink)
    out = np.zeros((size, size), dtype=bool)
    if len(xs) == 0:
        return out
    crop = ink[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    im = Image.fromarray((crop.astype(np.uint8) * 255), mode="L")
    im.thumbnail((size, size), Image.Resampling.BILINEAR)
    arr = np.array(im) >= 128
    y0 = (size - arr.shape[0]) // 2
    x0 = (size - arr.shape[1]) // 2
    out[y0 : y0 + arr.shape[0], x0 : x0 + arr.shape[1]] = arr
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def uniname(ch: str) -> str:
    return f"uni{ord(ch):04X}"


def sheet(pairs: list[tuple[str, np.ndarray, np.ndarray, float]], dest: Path) -> None:
    from PIL import Image, ImageDraw

    cell = 200
    pad = 8
    rows = len(pairs)
    page = Image.new("RGB", (cell * 3 + pad * 4, rows * (cell + 28) + pad), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    for i, (ch, ref, rec, score) in enumerate(pairs):
        y = pad + i * (cell + 28)
        ref_im = Image.fromarray((~ref).astype(np.uint8) * 255).convert("RGB")
        rec_im = Image.fromarray((~rec).astype(np.uint8) * 255).convert("RGB")
        xor = np.logical_xor(ref, rec)
        diff = np.zeros((cell, cell, 3), dtype=np.uint8)
        diff[:] = 255
        diff[xor] = (220, 0, 0)
        page.paste(ref_im, (pad, y))
        page.paste(rec_im, (pad * 2 + cell, y))
        page.paste(Image.fromarray(diff), (pad * 3 + cell * 2, y))
        draw.text((pad, y + cell + 2), f"{ch} IoU {score:.4f}", fill=(0, 0, 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.save(dest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract features from a reference font and rebuild")
    ap.add_argument("--ref", type=Path, default=REF_DEFAULT)
    ap.add_argument("--chars", default="十ニ三口日")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--mode", choices=("exact", "invert"), default="exact")
    ap.add_argument("--min-iou", type=float, default=None)
    args = ap.parse_args(argv)

    if not args.ref.is_file():
        print(f"error: missing ref {args.ref}", file=sys.stderr)
        return 2
    scratch = assert_throwaway(SCRATCH)
    scratch.mkdir(parents=True, exist_ok=True)
    ufo = scratch / "reproduce.ufo"
    built = scratch / ("reproduce.ttf" if args.mode == "exact" else "reproduce.otf")

    features: dict[str, dict] = {}
    if args.mode == "exact":
        features = subset_exact(args.ref, args.chars, built)
    else:
        glyphs: dict[str, tuple[int, list]] = {}
        for ch in args.chars:
            canvas = render_em(args.ref, ch)
            contours, feat = rebuild_contours(canvas)
            glyphs[uniname(ch)] = (ord(ch), contours)
            features[ch] = feat
        write_ufo(ufo, glyphs)
        from engine.bridge import compile_otf

        compile_otf(ufo, built, remove_overlaps=False)

    pairs = []
    rows = []
    for ch in args.chars:
        ref_c = render_em(args.ref, ch)
        rec_c = render_em(built, ch)
        if args.mode == "exact":
            score = iou(ref_c >= INK, rec_c >= INK)
        else:
            score = iou(pack_bbox(ref_c), pack_bbox(rec_c))
        pairs.append((ch, pack_bbox(ref_c), pack_bbox(rec_c), score))
        extra = features.get(ch, {})
        rows.append({"char": ch, "iou": round(score, 6), **extra})
        print(f"{ch} IoU={score:.6f}")

    png = args.out / "compare.png"
    sheet(pairs, png)
    mean = float(np.mean([p[3] for p in pairs]))
    report = {
        "mode": args.mode,
        "ref": str(args.ref),
        "shipping_ufo_written": False,
        "mean_iou": round(mean, 6),
        "glyphs": rows,
        "png": str(png),
    }
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"mean IoU={mean:.6f} {png}")
    floor = args.min_iou
    if floor is None:
        floor = 1.0 if args.mode == "exact" else 0.0
    if mean + 1e-12 < floor:
        print(f"error: mean IoU {mean:.6f} < {floor}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
