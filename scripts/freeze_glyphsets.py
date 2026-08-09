#!/usr/bin/env python3
"""常用・教育漢字リストを data/ に凍結（掟19）。PyPI kanji-lists から再生成。

Usage:
  python scripts/freeze_glyphsets.py          # 再生成
  python scripts/freeze_glyphsets.py --check  # 既存ファイルと一致するか検証のみ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _chars_from_kanji_lists() -> tuple[list[str], list[str]]:
    from kanji_lists import JOYO, KYOIKU

    joyo = sorted(JOYO, key=lambda c: ord(c))
    kyoiku = sorted(KYOIKU, key=lambda c: ord(c))
    if len(joyo) != 2136 or len(kyoiku) != 1026:
        raise SystemExit(f"unexpected counts: JOYO={len(joyo)} KYOIKU={len(kyoiku)}")
    if not set(kyoiku).issubset(set(joyo)):
        raise SystemExit("KYOIKU is not a subset of JOYO")
    return joyo, kyoiku


def _read_chars(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify existing freezes only")
    args = ap.parse_args(argv)

    try:
        joyo, kyoiku = _chars_from_kanji_lists()
    except ImportError:
        print("error: pip install kanji-lists", file=sys.stderr)
        return 2

    joyo_path = DATA / "glyphset_joyo2136.txt"
    kyoiku_path = DATA / "glyphset_kyoiku1026.txt"
    uni_path = DATA / "glyphset_joyo2136_uninames.txt"

    if args.check:
        if not joyo_path.is_file() or not kyoiku_path.is_file():
            print("error: frozen files missing", file=sys.stderr)
            return 1
        ok = _read_chars(joyo_path) == joyo and _read_chars(kyoiku_path) == kyoiku
        print("match" if ok else "MISMATCH")
        return 0 if ok else 1

    DATA.mkdir(parents=True, exist_ok=True)
    joyo_path.write_text("\n".join(joyo) + "\n", encoding="utf-8")
    kyoiku_path.write_text("\n".join(kyoiku) + "\n", encoding="utf-8")
    uni_path.write_text("\n".join(f"uni{ord(c):04X}" for c in joyo) + "\n", encoding="utf-8")
    print(f"froze JOYO={len(joyo)} KYOIKU={len(kyoiku)} → {DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
