#!/usr/bin/env python3
"""組見本生成ラッパ（S4）。uharfbuzz/hb-view を第一候補とし、自作は薄く保つ。

Usage:
  python scripts/make_proofs.py --font path/to.otf
  python scripts/make_proofs.py --font path/to.otf --faces ui,hud
  python scripts/make_proofs.py --font path/to.otf --compare-golden
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTS_DIR = ROOT / "proofs" / "texts"
OUT_DIR = ROOT / "proofs" / "out"
GOLDEN_DIR = ROOT / "proofs" / "golden"

# PLAN §7.1 S4: 主＝ui/hud、副＝literary（参考観測）
FACE_ORDER = ("ui", "hud", "literary")
PRIMARY_FACES = frozenset({"ui", "hud"})


def _load_text(face: str) -> str:
    path = TEXTS_DIR / f"{face}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"proof text missing: {path}")
    return path.read_text(encoding="utf-8").rstrip() + "\n"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def render_hb_view(font: Path, text: str, out_png: Path, font_size: int = 48) -> dict:
    hb_view = shutil.which("hb-view")
    if not hb_view:
        return {"ok": False, "skipped": True, "reason": "hb-view not found"}
    out_png.parent.mkdir(parents=True, exist_ok=True)
    # 複数行は argv 埋め込みだと環境依存で崩れるため、行を順に描画して縦連結する
    # （単一行なら 1 回で済む）。フォールバック経路と同型のページを目指す。
    lines = text.splitlines() or [""]
    if len(lines) == 1:
        cmd = [
            hb_view,
            "-o",
            str(out_png),
            "-O",
            "png",
            f"--font-size={font_size}",
            str(font),
            lines[0],
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        return {
            "ok": p.returncode == 0 and out_png.is_file(),
            "skipped": False,
            "cmd": cmd,
            "returncode": p.returncode,
            "stderr_tail": (p.stderr or "")[-400:],
            "png": str(out_png) if out_png.is_file() else None,
        }

    try:
        from PIL import Image
    except ImportError:
        return {
            "ok": False,
            "skipped": True,
            "reason": "multiline hb-view needs Pillow to stitch lines",
        }

    import tempfile

    line_pngs: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for i, line in enumerate(lines):
            lp = tmp_path / f"line_{i:03d}.png"
            cmd = [
                hb_view,
                "-o",
                str(lp),
                "-O",
                "png",
                f"--font-size={font_size}",
                str(font),
                line if line else " ",
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            if p.returncode != 0 or not lp.is_file():
                return {
                    "ok": False,
                    "skipped": False,
                    "cmd": cmd,
                    "returncode": p.returncode,
                    "stderr_tail": (p.stderr or "")[-400:],
                    "png": None,
                }
            line_pngs.append(lp)
        images = []
        for lp_path in line_pngs:
            with Image.open(lp_path) as im:
                images.append(im.convert("L").copy())
        gap = 8
        width = max(im.width for im in images)
        height = sum(im.height for im in images) + gap * (len(images) - 1)
        page = Image.new("L", (width, height), color=255)
        y = 0
        for im in images:
            page.paste(im, (0, y))
            y += im.height + gap
        page.save(out_png)
    return {
        "ok": out_png.is_file(),
        "skipped": False,
        "backend": "hb-view+stitch",
        "png": str(out_png) if out_png.is_file() else None,
    }


def render_uharfbuzz_freetype(
    font: Path, text: str, out_png: Path, em_px: int = 64
) -> dict:
    """hb-view が無い環境向けフォールバック（spike3 実証経路）。"""
    try:
        import freetype
        import numpy as np
        import uharfbuzz as hb
        from PIL import Image
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"deps missing: {e}"}

    data = font.read_bytes()
    face_hb = hb.Face(data)
    font_hb = hb.Font(face_hb)
    lines = text.splitlines() or [""]
    scale = em_px / face_hb.upem
    face_ft = freetype.Face(str(font))
    face_ft.set_pixel_sizes(em_px, em_px)

    line_canvases: list = []
    for line in lines:
        if not line:
            line_canvases.append(np.zeros((em_px + 16, em_px, ), dtype=np.uint8))
            continue
        buf = hb.Buffer()
        buf.add_str(line)
        buf.guess_segment_properties()
        hb.shape(font_hb, buf)
        positions = buf.glyph_positions
        infos = buf.glyph_infos
        total_adv = sum(pos.x_advance for pos in positions) * scale
        height = em_px + 24
        width = max(int(total_adv) + 40, em_px)
        canvas = np.zeros((height, width), dtype=np.uint8)
        pen_x = 12.0
        baseline = int(em_px * 0.85)
        for info, pos in zip(infos, positions):
            gid = info.codepoint
            face_ft.load_glyph(gid, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
            glyph = face_ft.glyph
            bitmap = glyph.bitmap
            w, h, pitch = bitmap.width, bitmap.rows, bitmap.pitch
            if w > 0 and h > 0:
                buf_b = bytes(bitmap.buffer)
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
            pen_x += pos.x_advance * scale
        line_canvases.append(canvas)

    max_w = max(c.shape[1] for c in line_canvases)
    total_h = sum(c.shape[0] for c in line_canvases) + 8 * (len(line_canvases) - 1)
    page = np.zeros((total_h, max_w), dtype=np.uint8)
    y = 0
    for c in line_canvases:
        page[y : y + c.shape[0], : c.shape[1]] = c
        y += c.shape[0] + 8

    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(255 - page, mode="L").save(out_png)
    return {"ok": out_png.is_file(), "skipped": False, "png": str(out_png), "backend": "uharfbuzz+freetype"}


def render_face(font: Path, face: str, out_dir: Path) -> dict:
    text = _load_text(face)
    out_png = out_dir / f"{face}.png"
    result = render_hb_view(font, text, out_png)
    if result.get("ok"):
        result["face"] = face
        result["backend"] = result.get("backend") or "hb-view"
        result["primary"] = face in PRIMARY_FACES
        result["sha256"] = _sha256(out_png)
        return result
    # hb-view 欠落でも失敗でもフォールバック（失敗時にフォールバックしないとゲートが死ぬ）
    hb_err = result
    fb = render_uharfbuzz_freetype(font, text, out_png)
    fb["face"] = face
    fb["primary"] = face in PRIMARY_FACES
    fb["hb_view"] = {
        "skipped": bool(hb_err.get("skipped")),
        "ok": bool(hb_err.get("ok")),
        "returncode": hb_err.get("returncode"),
        "reason": hb_err.get("reason") or hb_err.get("stderr_tail"),
    }
    if fb.get("ok"):
        fb["sha256"] = _sha256(out_png)
        return fb
    # 両方失敗
    result["face"] = face
    result["primary"] = face in PRIMARY_FACES
    result["fallback"] = fb
    return result


def compare_golden(face: str, out_png: Path) -> dict:
    golden = GOLDEN_DIR / f"{face}.png"
    if not golden.is_file():
        return {"compared": False, "reason": "no golden"}
    same = _sha256(out_png) == _sha256(golden)
    return {"compared": True, "match": same, "golden": str(golden)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate MyMincho proof images (S4)")
    ap.add_argument("--font", required=True, type=Path, help="OTF/TTF path")
    ap.add_argument(
        "--faces",
        default="ui,hud,literary",
        help="comma-separated faces (default: ui,hud,literary)",
    )
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    ap.add_argument(
        "--compare-golden",
        action="store_true",
        help="compare SHA256 against proofs/golden/*.png",
    )
    args = ap.parse_args(argv)

    font = args.font.resolve()
    if not font.is_file():
        print(f"error: font not found: {font}", file=sys.stderr)
        return 2

    faces = [f.strip() for f in args.faces.split(",") if f.strip()]
    for f in faces:
        if f not in FACE_ORDER:
            print(f"error: unknown face {f!r}; choose from {FACE_ORDER}", file=sys.stderr)
            return 2

    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    failed = False
    for face in faces:
        r = render_face(font, face, args.out)
        if args.compare_golden:
            if not (r.get("ok") and r.get("png")):
                failed = True
            else:
                r["golden"] = compare_golden(face, Path(r["png"]))
                # 黄金が無い／不一致はいずれも不合格（フラグ指定時に黙殺しない）
                if not r["golden"].get("compared") or not r["golden"].get("match"):
                    failed = True
        if not r.get("ok"):
            failed = True
        results.append(r)
        status = "ok" if r.get("ok") else ("skip" if r.get("skipped") else "FAIL")
        role = "primary" if r.get("primary") else "secondary"
        print(f"[{status}] {face} ({role}) backend={r.get('backend')} png={r.get('png')}")
        if r.get("stderr_tail"):
            print(f"  stderr: {r['stderr_tail'][:200]}")
        if r.get("golden"):
            print(f"  golden: {r['golden']}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
