#!/usr/bin/env python3
"""P-Q3 端物コンタクトシートと濁点サイズ表。合否ゲートではない。

例:
  engine/.venv/bin/python scripts/make_q3_sheet.py
  engine/.venv/bin/python scripts/make_q3_sheet.py --otf fonts_out/build/MyMincho.otf
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_OTF = ROOT / "fonts_out" / "build" / "MyMincho.otf"
DEFAULT_OUT = ROOT / "proofs" / "q3_diagnosis.md"
DAKUTEN_CHARS = "がじづぞぼ"
TERMINAL_CHARS = "あかきたてくすめやしん"
EXPECTED_CONTOURS = {"が": 5, "じ": 3, "づ": 3, "ぞ": 3, "ぼ": 6}
SIZE_FRAC = 0.15
SMALL_AREA_FRAC = 0.15

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receive_manual  # noqa: E402


def _load_ref_compare():
    path = ROOT / "engine" / "scripts" / "kana_ref_compare.py"
    spec = importlib.util.spec_from_file_location("kana_ref_compare", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def contour_metrics(contour) -> dict:
    xs = [p.x for p in contour]
    ys = [p.y for p in contour]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    w = xmax - xmin
    h = ymax - ymin
    return {
        "area": receive_manual.signed_area(contour),
        "w": w,
        "h": h,
        "max_dim": max(w, h),
        "cx": (xmin + xmax) / 2.0,
        "cy": (ymin + ymax) / 2.0,
    }


def pick_dakuten(glyph, n: int = 2) -> list[dict]:
    """小さい正輪郭のうち、右上寄りの n 個を濁点とみなす。穴は無視。"""
    positives: list[dict] = []
    for contour in glyph:
        m = contour_metrics(contour)
        if m["area"] > 0:
            positives.append(m)
    if len(positives) < n:
        return []
    total = sum(m["area"] for m in positives)
    small = [m for m in positives if m["area"] < SMALL_AREA_FRAC * total]
    pool = small if len(small) >= n else positives
    pool = sorted(pool, key=lambda m: m["cx"] + m["cy"], reverse=True)
    marks = pool[:n]
    return sorted(marks, key=lambda m: m["area"])


def classify_dakuten(row: dict, median_max_dim: float | None) -> list[str]:
    groups: list[str] = []
    if row["contours"] == 0:
        return ["欠字"]
    expected = row.get("expected_contours")
    if expected is not None and row["contours"] != expected:
        groups.append("輪郭数ずれ")
    if len(row.get("marks") or []) < 2:
        groups.append("濁点不足")
    if (
        median_max_dim
        and median_max_dim > 0
        and row.get("pair_max_dim") is not None
        and abs(row["pair_max_dim"] - median_max_dim) / median_max_dim > SIZE_FRAC
    ):
        groups.append("濁点サイズ外れ")
    return groups


def dakuten_rows(ufo: Path, chars: str = DAKUTEN_CHARS) -> list[dict]:
    from ufoLib2 import Font

    font = Font.open(ufo)
    rows: list[dict] = []
    for ch in chars:
        name = receive_manual.uni_name(ch)
        expected = EXPECTED_CONTOURS.get(ch)
        if name not in font or len(font[name]) == 0:
            rows.append(
                {
                    "char": ch,
                    "name": name,
                    "contours": 0,
                    "expected_contours": expected,
                    "marks": [],
                    "pair_area": None,
                    "pair_max_dim": None,
                    "groups": ["欠字"],
                }
            )
            continue
        glyph = font[name]
        marks = pick_dakuten(glyph)
        pair_area = sum(m["area"] for m in marks) if marks else None
        pair_max = max((m["max_dim"] for m in marks), default=None)
        rows.append(
            {
                "char": ch,
                "name": name,
                "contours": len(glyph),
                "expected_contours": expected,
                "marks": marks,
                "pair_area": pair_area,
                "pair_max_dim": pair_max,
                "groups": [],
            }
        )
    dims = [r["pair_max_dim"] for r in rows if r.get("pair_max_dim")]
    mid = median(dims) if dims else None
    for row in rows:
        if row["groups"] == ["欠字"]:
            continue
        row["groups"] = classify_dakuten(row, mid)
    return rows


def render_table(rows: list[dict]) -> str:
    lines = [
        "# P-Q3 端物／濁点シート",
        "",
        "合否ではない。エンジン端物テンプレ（F9）は手描きに押し付けない。",
        "濁点は正面積の小さい輪郭のうち右上寄りの2つ。穴は無視。",
        "サイズ外れはセット中央値から15%超（観測。帯にしない）。",
        "",
        "見る順: 1) `q3_dakuten.png` で濁点の大きさ 2) `q3_dakuten_crop.png` で点の形",
        "3) `q3_terminals.png` で打ち込みの入口角と抜きの向き。矛盾したら作業 UFO だけ直す。",
        "",
        "| 字 | contours | 期待 | 点1面積 | 点1max | 点2面積 | 点2max | 対max | 群 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        marks = row.get("marks") or []
        m1 = marks[0] if len(marks) > 0 else None
        m2 = marks[1] if len(marks) > 1 else None

        def _f(mark, key):
            if mark is None or mark.get(key) is None:
                return ""
            return f"{mark[key]:.1f}"

        expected = row.get("expected_contours")
        pair = row.get("pair_max_dim")
        groups = ",".join(row["groups"]) if row["groups"] else ""
        lines.append(
            f"| {row['char']} | {row['contours']} | "
            f"{'' if expected is None else expected} | "
            f"{_f(m1, 'area')} | {_f(m1, 'max_dim')} | "
            f"{_f(m2, 'area')} | {_f(m2, 'max_dim')} | "
            f"{'' if pair is None else f'{pair:.1f}'} | {groups} |"
        )

    def _group(name: str) -> list[str]:
        return [r["char"] for r in rows if name in r["groups"]]

    lines += [
        "",
        "## 群",
        "",
        f"- 欠字: {''.join(_group('欠字')) or 'なし'}",
        f"- 輪郭数ずれ: {''.join(_group('輪郭数ずれ')) or 'なし'}",
        f"- 濁点不足: {''.join(_group('濁点不足')) or 'なし'}",
        f"- 濁点サイズ外れ: {''.join(_group('濁点サイズ外れ')) or 'なし'}",
        "",
        "## 手直し",
        "",
        "- 正本 `fonts_out/MyMincho.ufo` を Glyphs で開かない",
        "- 描くのは `fonts_out/manual_kana/{字}.ufo`（`export_manual_work.py` 済）",
        "- 受け入れ: `receive_manual.py が じ づ ぞ ぼ`（既受付字を全部並べる）",
        "- し・く・っの本体は触らない。濁点5字の点だけを揃えるのが先",
        "",
    ]
    return "\n".join(lines) + "\n"


def _pad_cell(arr, cell: int):
    import numpy as np

    h, w = arr.shape
    out = np.zeros((cell, cell), dtype=np.uint8)
    y0 = max(0, (cell - h) // 2)
    x0 = max(0, (cell - w) // 2)
    y1 = min(cell, y0 + h)
    x1 = min(cell, x0 + w)
    out[y0:y1, x0:x1] = arr[: y1 - y0, : x1 - x0]
    return out


def _crop_ur(arr, frac_x: float = 0.42, frac_y: float = 0.45):
    h, w = arr.shape
    x0 = int(w * (1.0 - frac_x))
    y1 = max(1, int(h * frac_y))
    return arr[:y1, x0:]


def write_sheet(tiles_rows: list[list], out_png: Path, gap: int = 6) -> None:
    import numpy as np
    from PIL import Image

    if not tiles_rows or not any(tiles_rows):
        return
    row_h = max(max(t.shape[0] for t in tiles) for tiles in tiles_rows if tiles)
    row_w = max(
        sum(t.shape[1] for t in tiles) + gap * (len(tiles) - 1)
        for tiles in tiles_rows
        if tiles
    )
    page = np.zeros(
        (row_h * len(tiles_rows) + gap * (len(tiles_rows) - 1), row_w),
        dtype=np.uint8,
    )
    y = 0
    for tiles in tiles_rows:
        x = 0
        for t in tiles:
            page[y : y + t.shape[0], x : x + t.shape[1]] = t
            x += t.shape[1] + gap
        y += row_h + gap
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(255 - page, mode="L").save(out_png)


def render_rows(otf: Path, chars: str, em_px: int, cell: int | None = None):
    ref = _load_ref_compare()
    tiles = []
    for ch in chars:
        arr = ref.render_char(otf, ch, em_px=em_px)
        tiles.append(_pad_cell(arr, cell) if cell else arr)
    return tiles


def write_contact_sheets(otf: Path, out_dir: Path) -> list[Path]:
    ref = _load_ref_compare()
    ipaex = ref.REFERENCE_FONTS.get("ipaex")
    have_ipaex = bool(ipaex) and Path(ipaex).is_file()
    written: list[Path] = []

    dakuten = render_rows(otf, DAKUTEN_CHARS, 256, cell=280)
    rows = [dakuten]
    if have_ipaex:
        rows.append(render_rows(ipaex, DAKUTEN_CHARS, 256, cell=280))
    path = out_dir / "q3_dakuten.png"
    write_sheet(rows, path)
    written.append(path)

    crops = [_crop_ur(t) for t in dakuten]
    crop_rows = [crops]
    if have_ipaex:
        crop_rows.append([_crop_ur(t) for t in rows[1]])
    path = out_dir / "q3_dakuten_crop.png"
    write_sheet(crop_rows, path)
    written.append(path)

    terminals = render_rows(otf, TERMINAL_CHARS, 256, cell=280)
    t_rows = [terminals]
    if have_ipaex:
        t_rows.append(render_rows(ipaex, TERMINAL_CHARS, 256, cell=280))
    t_rows.append(render_rows(otf, TERMINAL_CHARS, 24))
    path = out_dir / "q3_terminals.png"
    write_sheet(t_rows, path)
    written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Q3 dakuten/terminal sheets (not a gate)")
    ap.add_argument("--ufo", type=Path, default=DEFAULT_UFO)
    ap.add_argument("--otf", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if not args.ufo.is_dir():
        print(f"error: missing UFO {args.ufo}", file=sys.stderr)
        return 2
    rows = dakuten_rows(args.ufo)
    text = render_table(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"wrote {args.out}")

    otf = args.otf if args.otf is not None else (
        DEFAULT_OTF if DEFAULT_OTF.is_file() else None
    )
    if otf is not None and otf.is_file():
        for path in write_contact_sheets(otf, args.out.parent):
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
