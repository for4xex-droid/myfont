"""必須39字とグリフ名。仕様の収録以外は名前にしない。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

# Adobe Glyph List。大文字はそのまま、数字は英単語、スラッシュは slash、空白は space。
# U+00A0 は AGL に名前がないので uniXXXX 形式にする。
_PAIRS: tuple[tuple[str, str], ...] = (
    *((chr(ord("A") + i), chr(ord("A") + i)) for i in range(26)),
    ("0", "zero"),
    ("1", "one"),
    ("2", "two"),
    ("3", "three"),
    ("4", "four"),
    ("5", "five"),
    ("6", "six"),
    ("7", "seven"),
    ("8", "eight"),
    ("9", "nine"),
    ("/", "slash"),
    (" ", "space"),
    ("\u00a0", "uni00A0"),
)

REQUIRED_CHARS: tuple[str, ...] = tuple(ch for ch, _ in _PAIRS)
GLYPH_NAMES: tuple[str, ...] = tuple(name for _, name in _PAIRS)

_BY_CHAR = dict(_PAIRS)
_BY_NAME = {name: ch for ch, name in _PAIRS}

# 空白は1字では書けないので U+XXXX で書く（大文字16進・4〜6桁）。ship_gate と同じ記法。
_CODEPOINT_LINE = re.compile(r"U\+([0-9A-F]{4,6})")


def glyph_name(ch: str) -> str:
    """文字をグリフ名にする。収録外は ValueError。"""
    try:
        return _BY_CHAR[ch]
    except KeyError:
        raise ValueError(f"not in required latin set: {ch!r}") from None


def character(name: str) -> str:
    """グリフ名を文字に戻す。未知の名前は ValueError。"""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ValueError(f"not a glyph name in the required latin set: {name!r}") from None


def reject_outside(chars: Iterable[str]) -> None:
    """収録外の字が1つでもあれば ValueError。空は通す。"""
    outside = [ch for ch in chars if ch not in _BY_CHAR]
    if outside:
        shown = ", ".join(repr(ch) for ch in outside)
        raise ValueError(f"outside required latin set: {shown}")


def _line_char(path: Path, i: int, line: str) -> str:
    m = _CODEPOINT_LINE.fullmatch(line)
    if m is not None:
        cp = int(m.group(1), 16)
        if cp == 0 or cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            raise ValueError(f"{path}: line {i} is not a Unicode scalar value: {line!r}")
        return chr(cp)
    if len(line) != 1:
        raise ValueError(f"{path}: line {i} must be exactly 1 character or U+XXXX, got {line!r}")
    return line


def read_glyphset_file(path: Path) -> tuple[str, ...]:
    """1行1字（または U+XXXX）の glyphset を読む。空・複数字・重複は ValueError。

    収録に入っているかは見ない。呼び側が reject_outside に渡す。
    BOM 付き UTF-8 は先頭の印を外して読む。
    """
    path = Path(path)
    chars: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ch = _line_char(path, i, line)
        if ch in seen:
            raise ValueError(f"{path}: line {i} duplicates {ch!r}")
        seen.add(ch)
        chars.append(ch)
    if not chars:
        raise ValueError(f"{path}: glyphset is empty")
    return tuple(chars)
