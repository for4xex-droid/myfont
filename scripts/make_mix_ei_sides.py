#!/usr/bin/env python3
"""永の左右はらいだけ 24 点点列にした混植捨てシート。正本 UFO は書かない。

join20 の他字は mix_k1 のまま。product_r1 は触らない。
IPAex の残差座標は捨て UFO にだけ載せる（掟9。出荷禁止）。

例:
  engine/.venv/bin/python scripts/make_mix_ei_sides.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
SCRATCH = ROOT / "proofs" / "mix" / "_scratch"
DEFAULT_OUT = ROOT / "proofs" / "mix"
MIX_TEXT = ROOT / "proofs" / "texts" / "mix.txt"
EI_NAME = "uni6C38"
SIZES = (20, 48)
PREFIX = "mix_ei_sides"

sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from make_mix_probe import (  # noqa: E402
    KANJI_IDS,
    assert_throwaway_dest,
    copy_ship_ufo,
    missing_chars,
)


def _ipaex_hara_rings():
    """永の左右はらい残差を 24 点左右輪郭にする。IPAex 空間（Y上）。"""
    from extract_ref_elements import extract_char, glyph_recording, recording_to_path
    from pathops import difference
    from pathops import Path as OpsPath
    from rebuild_from_elements import (
        _is_junction,
        _ops_rings,
        _split_sides,
        absorb_extensions,
        absorb_junctions,
        close_open_junctions,
        fill_corners,
        merge_collinear,
        outline_from_sides,
        scalar_hara_paths,
        stems_path,
        HARA_SCALAR_K,
    )
    from reproduce_ref import REF_DEFAULT

    if not REF_DEFAULT.is_file():
        raise FileNotFoundError(f"missing reference font {REF_DEFAULT}")

    row = extract_char(REF_DEFAULT, "永")
    rec, _, upm, _ = glyph_recording(REF_DEFAULT, "永")
    exact = recording_to_path(rec)
    junctions = [t for t in row["terminals"] if _is_junction(t, row, exact)]
    real = [t for t in row["terminals"] if not _is_junction(t, row, exact)]
    merged = fill_corners(absorb_junctions(merge_collinear(row["stems"]), junctions))
    merged, real = absorb_extensions(merged, real, exact)
    merged = merge_collinear(close_open_junctions(merged, exact))
    residual = OpsPath()
    difference([exact], [stems_path(merged)], residual.getPen(), fix_winding=True)
    rings = _ops_rings(residual)

    out = []
    for term in real:
        role = term.get("role") or term["kind"]
        if role not in ("left_hara", "right_hara"):
            continue
        parts = scalar_hara_paths(term, rings)
        if not parts:
            continue
        combined = parts[0]
        if len(parts) > 1:
            from extract_ref_elements import combine, union

            combined = combine(parts, union)
        got = _ops_rings(combined)
        if not got:
            continue
        ring = max(got, key=len)
        sides = _split_sides(ring)
        if sides is None:
            continue
        path = outline_from_sides(*sides, k=HARA_SCALAR_K)
        side_rings = _ops_rings(path)
        if not side_rings:
            continue
        out.append({"role": role, "ring": side_rings[0], "upm": upm})
    if len(out) < 2:
        raise RuntimeError(f"expected left+right hara sides, got {len(out)}")
    return out


def _ipaex_to_engine(x: float, y: float, src_upm: float, dst_upm: float = 1000.0):
    return x * dst_upm / src_upm, dst_upm - y * dst_upm / src_upm


def _ring_bounds(ring: list[tuple[float, float]]) -> list[float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def map_ring(
    ring: list[tuple[float, float]],
    src_b: list[float],
    dst_b: list[float],
) -> list[tuple[float, float]]:
    sx = (dst_b[2] - dst_b[0]) / max(1e-6, src_b[2] - src_b[0])
    sy = (dst_b[3] - dst_b[1]) / max(1e-6, src_b[3] - src_b[1])
    return [
        (dst_b[0] + (x - src_b[0]) * sx, dst_b[1] + (y - src_b[1]) * sy)
        for x, y in ring
    ]


def _poly_bounds(poly) -> list[float]:
    xs = [p.x for p in poly]
    ys = [p.y for p in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def _engine_hara_targets(params):
    from engine.skeletons import char_ei
    from engine.strokes import StrokeKind, build_stroke

    out = []
    for i, stroke in enumerate(char_ei()):
        if stroke.kind not in (StrokeKind.LEFT_HARA, StrokeKind.RIGHT_HARA):
            continue
        polys = build_stroke(stroke, params)
        if not polys:
            continue
        out.append(
            {
                "idx": i,
                "kind": stroke.kind.value,
                "bbox": _poly_bounds(polys[0]),
            }
        )
    return out


def _match_hara(ipaex_items: list[dict], engine_items: list[dict]) -> list[tuple[dict, dict]]:
    used: set[int] = set()
    pairs = []
    for item in ipaex_items:
        want = "left_hara" if item["role"] == "left_hara" else "right_hara"
        cands = [
            (i, e)
            for i, e in enumerate(engine_items)
            if i not in used and e["kind"] == want
        ]
        if not cands:
            continue
        # 掠は啄より大きい。IPAex の left_hara は長い掠に合わせる。
        i, eng = max(
            cands,
            key=lambda t: (t[1]["bbox"][2] - t[1]["bbox"][0])
            * (t[1]["bbox"][3] - t[1]["bbox"][1]),
        )
        used.add(i)
        pairs.append((item, eng))
    if len(pairs) < 2:
        raise RuntimeError(f"failed to match IPAex hara to engine strokes: {len(pairs)}")
    return pairs


def build_ei_sides_contours(params=None) -> list[list[tuple[float, float]]]:
    """mix_k1 の軸画＋点＋はね＋啄に、IPAex 掠・磔の 24 点左右を載せる。"""
    from engine.bridge import extract_contours_xy, normalize_fill_winding, to_font_contours
    from engine.geometry import Vec2
    from engine.join_solver import pathops_union, poly_to_path, solve_glyph
    from engine.params import MIX_K1
    from engine.skeletons import char_ei

    params = MIX_K1 if params is None else params
    ipaex = _ipaex_hara_rings()
    converted = []
    for item in ipaex:
        ring = [_ipaex_to_engine(x, y, item["upm"]) for x, y in item["ring"]]
        converted.append({"role": item["role"], "ring": ring, "bbox": _ring_bounds(ring)})
    engine_hara = _engine_hara_targets(params)
    pairs = _match_hara(converted, engine_hara)
    replaced = {eng["idx"] for _, eng in pairs}
    keep = [s for i, s in enumerate(char_ei()) if i not in replaced]
    stems = solve_glyph(keep, params)
    mapped = []
    for item, eng in pairs:
        mapped.append(poly_to_path([Vec2(*p) for p in map_ring(item["ring"], item["bbox"], eng["bbox"])]))
    united = pathops_union([stems.path] + mapped)
    contours, _winding = normalize_fill_winding(to_font_contours(extract_contours_xy(united)))
    return contours


def replace_ei_glyph(ufo_dir: Path, contours: list[list[tuple[float, float]]]) -> None:
    import ufoLib2
    from engine.bridge import _draw_contours

    dest = assert_throwaway_dest(ufo_dir)
    font = ufoLib2.Font.open(dest)
    if EI_NAME not in font:
        raise KeyError(f"{EI_NAME} missing in {dest}")
    width = font[EI_NAME].width
    unicodes = list(font[EI_NAME].unicodes)
    del font[EI_NAME]
    glyph = font.newGlyph(EI_NAME)
    glyph.width = width
    glyph.unicodes = unicodes
    _draw_contours(glyph, contours)
    glyph.lib["com.mymincho.mix_ei_sides"] = True
    font.save()


def render_named(font: Path, text: str, out_dir: Path, prefix: str) -> list[dict]:
    import make_proofs as mp

    rows: list[dict] = []
    for size in SIZES:
        png = out_dir / f"{prefix}_{size}.png"
        result = mp.render_hb_view(font, text, png, font_size=size)
        if not result.get("ok"):
            result = mp.render_uharfbuzz_freetype(font, text, png, em_px=size)
        if not result.get("ok"):
            raise RuntimeError(f"render failed at {size}: {result}")
        rows.append(
            {
                "size": size,
                "png": str(png),
                "backend": result.get("backend") or "hb-view",
                "sha256": mp._sha256(png),
            }
        )
    return rows


def write_compare(k1_png: Path, sides_png: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw

    a = Image.open(k1_png).convert("RGB")
    b = Image.open(sides_png).convert("RGB")
    label = 22
    width = max(a.width, b.width)
    page = Image.new("RGB", (width, a.height + b.height + label * 2), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    draw.text((4, 2), "mix_k1 (engine hara)", fill=(0, 0, 0))
    page.paste(a, (0, label))
    draw.text((4, label + a.height + 2), "ei sides 24pt (throwaway)", fill=(0, 0, 0))
    page.paste(b, (0, label * 2 + a.height))
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.save(dest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Throwaway 永 24-pt hara mix probe")
    ap.add_argument("--params", default="mix_k1")
    ap.add_argument("--scratch", type=Path, default=SCRATCH)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if not SHIP_UFO.is_dir():
        print(f"error: missing shipping UFO {SHIP_UFO}", file=sys.stderr)
        return 2
    if not MIX_TEXT.is_file():
        print(f"error: missing {MIX_TEXT}", file=sys.stderr)
        return 2

    scratch = assert_throwaway_dest(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    dest_ufo = scratch / "MyMincho-mix-ei-sides.ufo"
    dest_otf = scratch / "MyMincho-mix-ei-sides.otf"
    regen_root = scratch / "regen_ei_sides"

    copy_ship_ufo(dest_ufo)

    from engine.bridge import build_temp_font, compile_otf
    from engine.params import PARAM_SETS
    from merge_engine_ufo import main as merge_main

    if args.params not in PARAM_SETS:
        print(f"error: unknown params {args.params}", file=sys.stderr)
        return 2

    built = build_temp_font(
        args.params,
        glyph_ids=list(KANJI_IDS),
        out_root=regen_root,
        family_name="MyMincho-mix-ei-sides",
        keep_ufo=True,
    )
    if not built.fill_check.get("ok"):
        print(f"error: engine fill_check {built.fill_check}", file=sys.stderr)
        return 1

    rc = merge_main(["--engine", str(built.ufo_dir), "--dest", str(dest_ufo)])
    if rc != 0:
        print("error: merge into scratch UFO failed", file=sys.stderr)
        return rc

    contours = build_ei_sides_contours(PARAM_SETS[args.params])
    replace_ei_glyph(dest_ufo, contours)
    compile_otf(dest_ufo, dest_otf, remove_overlaps=False)

    text = MIX_TEXT.read_text(encoding="utf-8").rstrip() + "\n"
    absent = missing_chars(dest_otf, text)
    if absent:
        print(f"error: mix text has missing glyphs: {''.join(absent)}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    renders = render_named(dest_otf, text, args.out, PREFIX)
    compare = args.out / "compare_k1_vs_ei_sides_48.png"
    k1_48 = args.out / "mix_k1_48.png"
    if not k1_48.is_file():
        k1_48 = args.out / "mix_48.png"
    if k1_48.is_file():
        write_compare(k1_48, args.out / f"{PREFIX}_48.png", compare)

    report = {
        "throwaway": True,
        "shipping_ufo_written": False,
        "params": args.params,
        "kanji_ids": list(KANJI_IDS),
        "patched": EI_NAME,
        "hara_model": "ipaex leftover left/right sides resampled to 24+24, bbox-mapped onto engine 掠/磔",
        "kept_engine": "TEN, HORIZONTAL, VERTICAL+hane, short LEFT_HARA (啄)",
        "scratch_ufo": str(dest_ufo),
        "scratch_otf": str(dest_otf),
        "n_contours": len(contours),
        "renders": renders,
        "compare": str(compare) if compare.is_file() else None,
        "verdict": None,
        "note": "作者が mix_ei_sides_48.png と compare_k1_vs_ei_sides_48.png を見て NOTE.md に記入",
    }
    report_path = args.out / "ei_sides_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {report_path}")
    for row in renders:
        print(f"  {row['size']}px {row['png']}")
    if compare.is_file():
        print(f"  compare {compare}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
