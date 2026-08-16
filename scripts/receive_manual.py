#!/usr/bin/env python3
"""手描き1字を正本へ受け入れ。他字は HEAD から戻す。

例:
  engine/.venv/bin/python scripts/receive_manual.py せ
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "fonts_out" / "MyMincho.ufo"
DEFAULT_SRC_ROOT = ROOT / "fonts_out" / "manual_kana"
DEFAULT_MANUAL = ROOT / "fonts_out" / "manual_glyphs.txt"
DEFAULT_OTF = ROOT / "fonts_out" / "build" / "MyMincho.otf"
DEFAULT_PROOFS = ROOT / "proofs" / "out"
MANUAL_LIB = "com.mymincho.manual"
JUNK_ABS_AREA = 80.0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_manual_otf  # noqa: E402
import make_proofs  # noqa: E402
import merge_manual_kana  # noqa: E402
import set_manual_sidebearings as sidebearings  # noqa: E402


def uni_name(char: str) -> str:
    return f"uni{ord(char):04X}"


def signed_area(contour) -> float:
    from engine.bridge import shoelace

    pts = [(p.x, p.y) for p in contour if p.type != "offcurve"]
    if len(pts) < 3:
        pts = [(p.x, p.y) for p in contour]
    return shoelace(pts)


def oncurve_count(glyph) -> int:
    n = 0
    for contour in glyph:
        for pt in contour:
            if pt.type != "offcurve":
                n += 1
    return n


def remove_junk_contours(glyph, *, min_abs_area: float = JUNK_ABS_AREA) -> list[float]:
    """正面積の微小輪郭だけ落とす。負面積（穴）は残す。"""
    removed: list[float] = []
    keep = []
    for contour in list(glyph):
        area = signed_area(contour)
        if area < 0 or abs(area) >= min_abs_area:
            keep.append(contour)
        else:
            removed.append(area)
    glyph.clearContours()
    for contour in keep:
        glyph.appendContour(contour)
    return removed


def ensure_manual_listed(path: Path, name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    action = "already"
    for line in lines:
        stripped = line.strip()
        reserved = stripped.lstrip("#").strip()
        if stripped == name:
            found = True
            out.append(line)
        elif reserved == name and stripped.startswith("#"):
            found = True
            action = "uncommented"
            out.append(name)
        else:
            out.append(line)
    if not found:
        if out and out[-1] != "":
            out.append("")
        out.append(name)
        action = "appended"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return action


def is_ufo(path: Path) -> bool:
    return (path / "glyphs" / "contents.plist").is_file()


def glif_relpath(ufo: Path, name: str) -> str:
    contents = ufo / "glyphs" / "contents.plist"
    mapping = plistlib.loads(contents.read_bytes())
    if name not in mapping:
        raise KeyError(f"{name} missing from {contents}")
    return f"glyphs/{mapping[name]}"


def restore_other_from_head(repo: Path, ufo: Path, keep: set[str]) -> list[str]:
    if not (repo / ".git").is_dir() and not (repo / ".git").is_file():
        raise RuntimeError(f"not a git repo: {repo}")
    ufo_rel = ufo.resolve().relative_to(repo.resolve()).as_posix()
    proc = subprocess.run(
        ["git", "status", "--porcelain", "-u", "--", ufo_rel],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    restored: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:]
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        path = raw.strip().strip('"')
        rel_inside = Path(path).as_posix()
        if rel_inside.startswith(ufo_rel + "/"):
            rel_inside = rel_inside[len(ufo_rel) + 1 :]
        if rel_inside in keep:
            continue
        if line[:2].strip().startswith("?"):
            continue
        r = subprocess.run(
            ["git", "restore", "--source=HEAD", "--", path],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"git restore failed: {path}")
        restored.append(path)
    return restored


def _copy_work_glyph(dest_font, work_path: Path, name: str, char: str) -> None:
    from ufoLib2 import Font

    work = Font.open(work_path)
    if name not in work or len(work[name]) == 0:
        raise RuntimeError(f"{work_path} has no contours for {name}")
    dest_font[name] = work[name].copy()
    dest_font[name].lib[MANUAL_LIB] = True
    dest_font[name].unicodes = [ord(char)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Receive one hand-drawn kana into dest UFO")
    ap.add_argument("char", help="one hiragana character, e.g. せ")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--src-root", type=Path, default=DEFAULT_SRC_ROOT)
    ap.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--otf", type=Path, default=DEFAULT_OTF)
    ap.add_argument("--proofs", type=Path, default=DEFAULT_PROOFS)
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--no-proofs", action="store_true")
    ap.add_argument(
        "--force",
        action="store_true",
        help="replace dest from work UFO even if dest already has contours",
    )
    args = ap.parse_args(argv)

    if len(args.char) != 1:
        print(f"error: expected one char, got {args.char!r}", file=sys.stderr)
        return 2
    if args.char in merge_manual_kana.ENGINE_CANONICAL:
        print(
            f"error: {args.char} is engine-canonical; refuse receive",
            file=sys.stderr,
        )
        return 2
    if not args.dest.is_dir():
        print(f"error: missing dest UFO {args.dest}", file=sys.stderr)
        return 2
    if not is_ufo(args.dest):
        print(
            f"error: not a UFO (missing glyphs/contents.plist): {args.dest}",
            file=sys.stderr,
        )
        return 2

    name = uni_name(args.char)
    work = args.src_root / f"{args.char}.ufo"
    from ufoLib2 import Font

    try:
        dest = Font.open(args.dest)
        if work.is_dir():
            dest_drawn = name in dest and len(dest[name]) > 0
            if dest_drawn and not args.force:
                print(
                    f"skip work {work}: dest already drawn "
                    f"({len(dest[name])} contours); pass --force to replace"
                )
            else:
                _copy_work_glyph(dest, work, name, args.char)
        if name not in dest or len(dest[name]) == 0:
            print(f"error: {name} has no contours (need work UFO or dest)", file=sys.stderr)
            return 2
        dest[name].lib[MANUAL_LIB] = True
        dest[name].unicodes = [ord(args.char)]
        removed = remove_junk_contours(dest[name])
        sidebearings.set_sidebearings(
            dest[name],
            lsb=sidebearings.TARGET_LSB,
            rsb=sidebearings.TARGET_RSB,
        )
        dest.save()
        keep = {"contents.plist", glif_relpath(args.dest, name)}
        restored = restore_other_from_head(args.repo, args.dest, keep)
        if not args.manual.is_file():
            print(f"error: missing {args.manual}", file=sys.stderr)
            return 2
        listed = ensure_manual_listed(args.manual, name)
        dest = Font.open(args.dest)
        glyph = dest[name]
        lsb, rsb, _ink = sidebearings.sidebearings(glyph)
        print(
            f"{args.char} {name} contours={len(glyph)} oncurve={oncurve_count(glyph)} "
            f"lsb={lsb:.1f} rsb={rsb:.1f} junk_removed={len(removed)} "
            f"restored={len(restored)} manual={listed}"
        )
        if removed:
            print(f"  junk_areas={removed}")
    except Exception as e:
        print(f"error: receive failed: {e}", file=sys.stderr)
        return 1

    if not args.no_compile:
        rc = compile_manual_otf.main(["--ufo", str(args.dest), "--otf", str(args.otf)])
        if rc != 0:
            return rc
    if not args.no_proofs:
        if not args.otf.is_file():
            print(f"error: missing OTF {args.otf}", file=sys.stderr)
            return 2
        rc = make_proofs.main(
            [
                "--font",
                str(args.otf),
                "--faces",
                "ui_kana,hud_kana,walk_kana",
                "--out",
                str(args.proofs),
            ]
        )
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
