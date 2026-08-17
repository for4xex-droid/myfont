#!/usr/bin/env python3
"""手描き仮名×エンジン漢字の混植捨てシート。正本 UFO は書かない。

例:
  engine/.venv/bin/python scripts/make_mix_probe.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP_UFO = ROOT / "fonts_out" / "MyMincho.ufo"
SCRATCH = ROOT / "proofs" / "mix" / "_scratch"
DEFAULT_OUT = ROOT / "proofs" / "mix"
MIX_TEXT = ROOT / "proofs" / "texts" / "mix.txt"
KANJI_IDS = ("juu", "ni", "san", "ei", "kuchi", "nichi", "ta", "naka")
SIZES = (20, 48)

sys.path.insert(0, str(ROOT / "engine" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def assert_throwaway_dest(dest: Path) -> Path:
    """正本と、正本の内側への書き込みを拒否する。"""
    dest = dest.resolve()
    ship = SHIP_UFO.resolve()
    if dest == ship or dest == ship.parent or ship in dest.parents or dest in ship.parents:
        raise ValueError(f"refuse to write mix probe into shipping UFO: {dest}")
    return dest


def copy_ship_ufo(dest_ufo: Path) -> Path:
    dest_ufo = assert_throwaway_dest(dest_ufo)
    if dest_ufo.exists():
        shutil.rmtree(dest_ufo)
    dest_ufo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SHIP_UFO, dest_ufo)
    return dest_ufo


def missing_chars(otf: Path, text: str) -> list[str]:
    from fontTools.ttLib import TTFont

    cmap = TTFont(otf).getBestCmap() or {}
    return sorted({c for c in text if c not in " \n" and ord(c) not in cmap})


def render_sizes(font: Path, text: str, out_dir: Path) -> list[dict]:
    import make_proofs as mp

    rows: list[dict] = []
    for size in SIZES:
        png = out_dir / f"mix_{size}.png"
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Throwaway kana+kanji mix probe")
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
    dest_ufo = scratch / "MyMincho-mix.ufo"
    dest_otf = scratch / "MyMincho-mix.otf"
    regen_root = scratch / "regen"

    copy_ship_ufo(dest_ufo)

    from engine.bridge import build_temp_font
    from merge_engine_ufo import main as merge_main
    from engine.bridge import compile_otf

    built = build_temp_font(
        args.params,
        glyph_ids=list(KANJI_IDS),
        out_root=regen_root,
        family_name="MyMincho-mix-engine",
        keep_ufo=True,
    )
    if not built.fill_check.get("ok"):
        print(f"error: engine fill_check {built.fill_check}", file=sys.stderr)
        return 1

    rc = merge_main(["--engine", str(built.ufo_dir), "--dest", str(dest_ufo)])
    if rc != 0:
        print("error: merge into scratch UFO failed", file=sys.stderr)
        return rc

    compile_otf(dest_ufo, dest_otf, remove_overlaps=False)
    text = MIX_TEXT.read_text(encoding="utf-8").rstrip() + "\n"
    absent = missing_chars(dest_otf, text)
    if absent:
        print(
            f"error: mix text has missing glyphs (fallback would contaminate): {''.join(absent)}",
            file=sys.stderr,
        )
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    renders = render_sizes(dest_otf, text, args.out)

    report = {
        "throwaway": True,
        "shipping_ufo_written": False,
        "params": args.params,
        "kanji_ids": list(KANJI_IDS),
        "engine_ufo": str(built.ufo_dir),
        "scratch_ufo": str(dest_ufo),
        "scratch_otf": str(dest_otf),
        "fill_check": built.fill_check,
        "measure_juu": built.measure_juu,
        "renders": renders,
        "verdict": None,
        "note": "作者が mix_20.png / mix_48.png を見て proofs/mix/NOTE.md に記入",
    }
    report_path = args.out / "mix_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {report_path}")
    for row in renders:
        print(f"  {row['size']}px {row['png']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
