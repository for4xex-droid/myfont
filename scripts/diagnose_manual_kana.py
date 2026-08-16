#!/usr/bin/env python3
"""手描き37字の「荒い」診断表（P-Q0）。合否ゲートではない。

例:
  engine/.venv/bin/python scripts/diagnose_manual_kana.py
  engine/.venv/bin/python scripts/diagnose_manual_kana.py --otf fonts_out/build/MyMincho.otf
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fontdb" / "src"))
DEFAULT_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_OTF = ROOT / "fonts_out" / "build" / "MyMincho.otf"
DEFAULT_OUT = ROOT / "proofs" / "q0_diagnosis.md"
P1_DRAWN = "あいうえおかきくけこさしすせそたちつてとのはひほまめやるりをんっがじづぞぼ"
POINT_HEAVY_PER_CONTOUR = 48.0
# 形状上これ以上減らせない（作者判断。合否ではない）
POINT_EXCEPTIONS = frozenset("るそ")
SMALL_DENSITY_FRAC = 0.15

sys.path.insert(0, str(Path(__file__).resolve().parent))
import set_manual_sidebearings as sidebearings  # noqa: E402


def _load_ref_compare():
    path = ROOT / "engine" / "scripts" / "kana_ref_compare.py"
    spec = importlib.util.spec_from_file_location("kana_ref_compare", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def oncurve_count(glyph) -> int:
    n = 0
    for contour in glyph:
        for pt in contour:
            if pt.type != "offcurve":
                n += 1
    return n


def classify(row: dict) -> list[str]:
    groups: list[str] = []
    if not row["in_band"]:
        groups.append("帯外")
    per = row["oncurve"] / max(1, row["contours"])
    if row.get("char") in POINT_EXCEPTIONS and per > POINT_HEAVY_PER_CONTOUR:
        groups.append("既知例外")
    elif per > POINT_HEAVY_PER_CONTOUR:
        groups.append("節点過多")
    if row.get("small_flag"):
        groups.append("小サイズで目立つ")
    return groups


def ufo_rows(ufo: Path, chars: str = P1_DRAWN) -> list[dict]:
    from ufoLib2 import Font

    font = Font.open(ufo)
    rows: list[dict] = []
    for ch in chars:
        name = f"uni{ord(ch):04X}"
        if name not in font or len(font[name]) == 0:
            rows.append(
                {
                    "char": ch,
                    "name": name,
                    "contours": 0,
                    "oncurve": 0,
                    "lsb": None,
                    "rsb": None,
                    "in_band": False,
                    "small_flag": False,
                    "groups": ["欠字"],
                }
            )
            continue
        glyph = font[name]
        lsb, rsb, ink = sidebearings.sidebearings(glyph)
        row = {
            "char": ch,
            "name": name,
            "contours": len(glyph),
            "oncurve": oncurve_count(glyph),
            "lsb": lsb,
            "rsb": rsb,
            "ink": ink,
            "in_band": sidebearings.in_band(lsb, rsb),
            "small_flag": False,
        }
        row["groups"] = classify(row)
        rows.append(row)
    return rows


def attach_raster(rows: list[dict], otf: Path) -> None:
    """OTF があるときだけ ink / ステム / 小サイズ外れを足す。参照書体は任意。"""
    from fontdb.metrics.ink import ink_metrics
    from fontdb.probes.juu_contrast import measure_juu_contrast

    ref = _load_ref_compare()
    ipaex = ref.REFERENCE_FONTS.get("ipaex")
    have_ipaex = bool(ipaex) and Path(ipaex).is_file()
    densities_20: list[float] = []
    skipped = 0
    for row in rows:
        if row["contours"] == 0:
            continue
        try:
            arr256 = ref.render_char(otf, row["char"], em_px=256)
            arr20 = ref.render_char(otf, row["char"], em_px=20)
        except Exception as e:
            skipped += 1
            print(f"raster skip {row['char']}: {e}", file=sys.stderr)
            continue
        scalars = ref.measure_scalars(arr256) or {}
        ink = ink_metrics(arr256, threshold=64, em_px=256)
        stem = measure_juu_contrast(arr256, threshold=64, em_px=256)
        m20 = ref.measure_scalars(arr20) or {}
        row["ink_density"] = scalars.get("ink_density")
        row["ink_confidence"] = "low_confidence"
        row["face_w"] = scalars.get("w_px")
        row["face_h"] = scalars.get("h_px")
        row["centroid_x"] = scalars.get("centroid_x_frac")
        row["centroid_y"] = scalars.get("centroid_y_frac")
        row["black_density"] = ink.get("black_density")
        row["face_ratio"] = ink.get("face_ratio")
        if stem.get("status") == "ok":
            row["stem_v"] = stem.get("vert_thickness_px")
            row["stem_h"] = stem.get("horiz_thickness_px")
            row["stem_v_em"] = (
                float(stem["vert_thickness_px"]) / 256.0
                if stem.get("vert_thickness_px") is not None
                else None
            )
            row["stem_h_em"] = (
                float(stem["horiz_thickness_px"]) / 256.0
                if stem.get("horiz_thickness_px") is not None
                else None
            )
        row["ink_density_20"] = m20.get("ink_density")
        if row.get("ink_density_20") is not None:
            densities_20.append(float(row["ink_density_20"]))
        row["small_arr"] = arr20
        if have_ipaex:
            try:
                ipa256 = ref.render_char(ipaex, row["char"], em_px=256)
                ipa20 = ref.render_char(ipaex, row["char"], em_px=20)
            except Exception as e:
                print(f"ipaex skip {row['char']}: {e}", file=sys.stderr)
                ipa256 = ipa20 = None
            if ipa256 is not None:
                ipa_s = ref.measure_scalars(ipa256) or {}
                row["ipaex_ink"] = ipa_s.get("ink_density")
            if ipa20 is not None:
                ipa20_s = ref.measure_scalars(ipa20) or {}
                row["ipaex_ink_20"] = ipa20_s.get("ink_density")
                row["ipaex_small_arr"] = ipa20

    used_ipaex = False
    for row in rows:
        ours = row.get("ink_density_20")
        theirs = row.get("ipaex_ink_20")
        if ours is not None and theirs and theirs > 0:
            used_ipaex = True
            if abs(ours - theirs) / theirs > SMALL_DENSITY_FRAC:
                row["small_flag"] = True
                row["groups"] = classify(row)
    if not used_ipaex and densities_20:
        mid = median(densities_20)
        if mid > 0:
            for row in rows:
                d = row.get("ink_density_20")
                if d is None:
                    continue
                if abs(d - mid) / mid > SMALL_DENSITY_FRAC:
                    row["small_flag"] = True
                    row["groups"] = classify(row)
    if skipped:
        print(f"raster skipped: {skipped}", file=sys.stderr)


def render_table(rows: list[dict]) -> str:
    lines = [
        "# P-Q0 手描き仮名診断",
        "",
        "合否ではない。`kana_targets.yaml` は未凍結のまま使わない。",
        "重ね塗りOTFの ink/stem は掟5で low_confidence（接合が二重カウント）。profile=`ft_256_nohint_gray`。stem は EM（px/256）。status≠ok は空欄。",
        "群: 帯外 / 節点過多（輪郭あたり oncurve > 48） / 小サイズで目立つ（20px ink が IPAex から15%超。無ければ自セット中央値）。",
        "",
        "| 字 | contours | oncurve | per | LSB | RSB | 群 | ink256 | ipaex | stemVem | stemHem | ink20 | ipaex20 |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        per = row["oncurve"] / max(1, row["contours"]) if row["contours"] else 0
        lsb = "" if row["lsb"] is None else f"{row['lsb']:.1f}"
        rsb = "" if row["rsb"] is None else f"{row['rsb']:.1f}"
        groups = ",".join(row["groups"]) if row["groups"] else ""
        ink = row.get("ink_density")
        stem_v = row.get("stem_v_em")
        stem_h = row.get("stem_h_em")
        ink20 = row.get("ink_density_20")
        ipa = row.get("ipaex_ink")
        ipa20 = row.get("ipaex_ink_20")
        lines.append(
            f"| {row['char']} | {row['contours']} | {row['oncurve']} | {per:.1f} | "
            f"{lsb} | {rsb} | {groups} | "
            f"{'' if ink is None else f'{ink:.3f}'} | "
            f"{'' if ipa is None else f'{ipa:.3f}'} | "
            f"{'' if stem_v is None else f'{stem_v:.3f}'} | "
            f"{'' if stem_h is None else f'{stem_h:.3f}'} | "
            f"{'' if ink20 is None else f'{ink20:.3f}'} | "
            f"{'' if ipa20 is None else f'{ipa20:.3f}'} |"
        )

    def _group(name: str) -> list[str]:
        return [r["char"] for r in rows if name in r["groups"]]

    lines += [
        "",
        "## 3群",
        "",
        f"- 帯外: {''.join(_group('帯外')) or 'なし'}",
        f"- 節点過多: {''.join(_group('節点過多')) or 'なし'}",
        f"- 既知例外: {''.join(_group('既知例外')) or 'なし'}",
        f"- 小サイズで目立つ: {''.join(_group('小サイズで目立つ')) or ('なし' if any(r.get('ink_density_20') is not None for r in rows) else 'なし（OTF未計測）')}",
        f"- 欠字: {''.join(_group('欠字')) or 'なし'}",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_small_sheet(rows: list[dict], out_png: Path) -> None:
    ours = [r["small_arr"] for r in rows if r.get("small_arr") is not None]
    if not ours:
        return
    import numpy as np
    from PIL import Image

    refs = [r.get("ipaex_small_arr") for r in rows if r.get("small_arr") is not None]
    rows_tiles = [ours]
    if any(t is not None for t in refs):
        rows_tiles.append([t if t is not None else np.zeros_like(ours[0]) for t in refs])

    row_h = max(max(t.shape[0] for t in tiles) for tiles in rows_tiles)
    row_w = max(sum(t.shape[1] for t in tiles) + 2 * (len(tiles) - 1) for tiles in rows_tiles)
    page = np.zeros((row_h * len(rows_tiles) + 4 * (len(rows_tiles) - 1), row_w), dtype=np.uint8)
    y = 0
    for tiles in rows_tiles:
        x = 0
        for t in tiles:
            page[y : y + t.shape[0], x : x + t.shape[1]] = t
            x += t.shape[1] + 2
        y += row_h + 4
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(255 - page, mode="L").save(out_png)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diagnose hand-drawn kana roughness (not a gate)")
    ap.add_argument("--ufo", type=Path, default=DEFAULT_UFO)
    ap.add_argument("--otf", type=Path, default=None)
    ap.add_argument("--chars", default=P1_DRAWN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if not args.ufo.is_dir():
        print(f"error: missing UFO {args.ufo}", file=sys.stderr)
        return 2
    rows = ufo_rows(args.ufo, chars=args.chars)
    otf = args.otf if args.otf is not None else (DEFAULT_OTF if DEFAULT_OTF.is_file() else None)
    sheet = None
    if otf is not None and otf.is_file():
        attach_raster(rows, otf)
        sheet = args.out.with_name("q0_small20.png")
        write_small_sheet(rows, sheet)
    text = render_table(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"wrote {args.out}")
    if sheet is not None and sheet.is_file():
        print(f"wrote {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
