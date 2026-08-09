#!/usr/bin/env python3
"""出荷ゲート CLI（S1）。OTF/TTF を入力に合否を一括判定する。

Usage:
  python engine/scripts/ship_gate.py path/to.otf --glyphset data/glyphset_alpha.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ASCENDER = 880
DEFAULT_DESCENDER = -120
DEFAULT_UPM = 1000


def load_glyphset(path: Path) -> list[str]:
    """1行1字の glyphset を読む。空・複数字行は ValueError（ゲートを黙殺させない）。"""
    chars: list[str] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) != 1:
            raise ValueError(f"{path}: line {i} must be exactly 1 character, got {line!r}")
        chars.append(line)
    if not chars:
        raise ValueError(f"{path}: glyphset is empty (comments-only is not a valid ship set)")
    return chars


def check_cmap_coverage(tt, glyphset: list[str]) -> dict:
    """欠字に加え、cmap が `.notdef` を指す字も missing 扱い（見せかけの充足を拒否）。"""
    if not glyphset:
        return {
            "name": "cmap_coverage",
            "ok": False,
            "missing_count": 0,
            "missing_sample": "",
            "glyphset_size": 0,
            "reason": "empty glyphset",
        }
    cmap = tt.getBestCmap() or {}
    missing: list[str] = []
    for ch in glyphset:
        cp = ord(ch)
        if cp not in cmap:
            missing.append(ch)
            continue
        if cmap[cp] == ".notdef":
            missing.append(ch)
    return {
        "name": "cmap_coverage",
        "ok": len(missing) == 0,
        "missing_count": len(missing),
        "missing_sample": "".join(missing[:40]),
        "glyphset_size": len(glyphset),
    }


def check_notdef(tt) -> dict:
    ok = ".notdef" in tt.getGlyphOrder()
    return {"name": "notdef", "ok": ok}


def check_metrics(
    tt,
    ascender: int,
    descender: int,
    upm: int = DEFAULT_UPM,
) -> dict:
    os2 = tt["OS/2"]
    hhea = tt["hhea"]
    issues = []
    units = int(tt["head"].unitsPerEm)
    if units != upm:
        issues.append(f"head.unitsPerEm={units} want {upm}")
    # Prefer sTypo* as design_rules source of truth; also check hhea
    typo_asc = int(os2.sTypoAscender)
    typo_desc = int(os2.sTypoDescender)
    hhea_asc = int(hhea.ascent)
    hhea_desc = int(hhea.descent)
    if typo_asc != ascender:
        issues.append(f"OS/2.sTypoAscender={typo_asc} want {ascender}")
    if typo_desc != descender:
        issues.append(f"OS/2.sTypoDescender={typo_desc} want {descender}")
    if hhea_asc != ascender:
        issues.append(f"hhea.ascent={hhea_asc} want {ascender}")
    if hhea_desc != descender:
        issues.append(f"hhea.descent={hhea_desc} want {descender}")
    return {
        "name": "vertical_metrics",
        "ok": len(issues) == 0,
        "issues": issues,
        "values": {
            "unitsPerEm": units,
            "sTypoAscender": typo_asc,
            "sTypoDescender": typo_desc,
            "hhea.ascent": hhea_asc,
            "hhea.descent": hhea_desc,
        },
    }


def check_name_table(tt) -> dict:
    name = tt["name"]
    required_ids = {
        1: "family",
        2: "subfamily",
        3: "unique_id",
        4: "full_name",
        6: "postscript",
    }
    present = {}
    for nid, label in required_ids.items():
        rec = name.getDebugName(nid)
        present[label] = bool(rec)
    copyright_or_license = bool(name.getDebugName(0) or name.getDebugName(13) or name.getDebugName(14))
    ok = all(present.values()) and copyright_or_license
    return {
        "name": "name_table",
        "ok": ok,
        "present": present,
        "copyright_or_license": copyright_or_license,
    }


def check_no_hangul_cmap(tt) -> dict:
    cmap = tt.getBestCmap() or {}
    hangul = [
        cp
        for cp in cmap
        if (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF) or (0x3130 <= cp <= 0x318F)
    ]
    return {
        "name": "no_hangul_cmap",
        "ok": len(hangul) == 0,
        "hangul_count": len(hangul),
    }


def check_layout_tables_absent_ok(tt) -> dict:
    """α/β: GSUB/GPOS 未搭載でよい。存在しても fail にはしない（情報のみ）。"""
    has_gsub = "GSUB" in tt
    has_gpos = "GPOS" in tt
    return {
        "name": "layout_tables",
        "ok": True,
        "GSUB": has_gsub,
        "GPOS": has_gpos,
        "note": "α/β may omit GSUB/GPOS",
    }


def check_outline_sample(font_path: Path) -> dict:
    """輪郭サンプル検査（pathops で描画・simplify 可能か）。

    注意: `Path.simplify` は自己交差の完全検出器ではない。
    本チェックは「輪郭が pathops で読める」ことのスモークであり、
    製品級の自己交差ゼロ証明は checkoutlinesufo / 専用検査に委ねる。
    pathops が無い場合は **fail**（未検証を ok にしない）。
    """
    try:
        import pathops
        from fontTools.ttLib import TTFont
    except ImportError:
        return {
            "name": "outline_sample",
            "ok": False,
            "skipped": True,
            "reason": "skia-pathops or fontTools unavailable (unverified ≠ pass)",
        }

    tt = TTFont(str(font_path))
    if "glyf" not in tt and "CFF " not in tt and "CFF2" not in tt:
        return {
            "name": "outline_sample",
            "ok": False,
            "skipped": True,
            "reason": "no outline table",
        }

    bad: list[str] = []
    cmap = tt.getBestCmap() or {}
    names = [".notdef"] + [cmap[cp] for cp in list(cmap)[:40]]
    glyph_set = tt.getGlyphSet()
    for gname in names:
        if gname not in glyph_set:
            continue
        try:
            path = pathops.Path()
            pen = path.getPen()
            glyph_set[gname].draw(pen)
            path.simplify(fix_winding=True)
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as e:
            bad.append(f"{gname}:{type(e).__name__}")
        if len(bad) >= 10:
            break

    return {
        "name": "outline_sample",
        "ok": len(bad) == 0,
        "bad_sample": bad,
        "skipped": False,
        "note": "smoke only; not a full self-intersection proof",
    }


def run_fontbakery(font_path: Path) -> dict:
    import shutil
    import subprocess

    exe = shutil.which("fontbakery")
    if not exe:
        # 明示要求した検査が未実行なら不合格（skip≠pass）
        return {
            "name": "fontbakery",
            "ok": False,
            "skipped": True,
            "reason": "fontbakery not found (requested via --fontbakery)",
        }
    p = subprocess.run(
        [exe, "check-universal", "--loglevel", "ERROR", str(font_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    # ERROR ログレベルでの非ゼロは不合格。WARN のみは 0 終了を想定。
    return {
        "name": "fontbakery",
        "ok": p.returncode == 0,
        "skipped": False,
        "returncode": p.returncode,
        "stderr_tail": (p.stderr or "")[-500:],
        "stdout_tail": (p.stdout or "")[-500:],
        "note": "fail on ERROR-level exit; whitelist TBD in docs/ship_gate_rules.md",
    }


def run_gate(
    font_path: Path,
    glyphset_path: Path,
    ascender: int = DEFAULT_ASCENDER,
    descender: int = DEFAULT_DESCENDER,
    upm: int = DEFAULT_UPM,
    with_fontbakery: bool = False,
) -> list[dict]:
    from fontTools.ttLib import TTFont

    tt = TTFont(str(font_path))
    results: list[dict] = []
    gs = load_glyphset(glyphset_path)
    results.append(check_cmap_coverage(tt, gs))
    results.append(check_notdef(tt))
    results.append(check_metrics(tt, ascender, descender, upm=upm))
    results.append(check_name_table(tt))
    results.append(check_no_hangul_cmap(tt))
    results.append(check_layout_tables_absent_ok(tt))
    results.append(check_outline_sample(font_path))
    if with_fontbakery:
        results.append(run_fontbakery(font_path))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MyMincho ship gate (S1)")
    ap.add_argument("font", type=Path, help="OTF/TTF path")
    ap.add_argument(
        "--glyphset",
        type=Path,
        required=True,
        help="glyphset txt (one char per line). Required — cmap skip is not a pass.",
    )
    ap.add_argument("--ascender", type=int, default=DEFAULT_ASCENDER)
    ap.add_argument("--descender", type=int, default=DEFAULT_DESCENDER)
    ap.add_argument("--upm", type=int, default=DEFAULT_UPM)
    ap.add_argument("--fontbakery", action="store_true", help="run fontbakery check-universal")
    args = ap.parse_args(argv)

    font = args.font.resolve()
    if not font.is_file():
        print(f"error: font not found: {font}", file=sys.stderr)
        return 2
    glyphset = args.glyphset.resolve()
    if not glyphset.is_file():
        print(f"error: glyphset not found: {glyphset}", file=sys.stderr)
        return 2

    try:
        from fontTools.ttLib import TTLibError
    except ImportError:
        TTLibError = RuntimeError  # type: ignore[misc,assignment]

    try:
        results = run_gate(
            font,
            glyphset,
            ascender=args.ascender,
            descender=args.descender,
            upm=args.upm,
            with_fontbakery=args.fontbakery,
        )
    except (OSError, ValueError, KeyError, RuntimeError, TTLibError) as e:
        print(f"error: failed to open font or glyphset: {e}", file=sys.stderr)
        return 2

    failed = False
    for r in results:
        # skipped かつ ok=False は未検証＝不合格（fail-open 禁止）
        if r.get("skipped") and not r.get("ok", False):
            status = "FAIL"
            failed = True
        elif r.get("skipped"):
            status = "skip"
        elif r.get("ok"):
            status = "ok"
        else:
            status = "FAIL"
            failed = True
        print(f"[{status}] {r['name']}: { {k: v for k, v in r.items() if k != 'name'} }")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
