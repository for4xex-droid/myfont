"""必須37字と AGL グリフ名。仕様の収録以外は名前にしない。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Adobe Glyph List。大文字はそのまま、数字は英単語、スラッシュは slash。
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
)

REQUIRED_CHARS: tuple[str, ...] = tuple(ch for ch, _ in _PAIRS)
GLYPH_NAMES: tuple[str, ...] = tuple(name for _, name in _PAIRS)

_BY_CHAR = dict(_PAIRS)
_BY_NAME = {name: ch for ch, name in _PAIRS}


def glyph_name(ch: str) -> str:
    """文字を AGL 名にする。収録外は ValueError。"""
    try:
        return _BY_CHAR[ch]
    except KeyError:
        raise ValueError(f"not in required latin set: {ch!r}") from None


def character(name: str) -> str:
    """AGL 名を文字に戻す。未知の名前は ValueError。"""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ValueError(f"not an AGL name in the required latin set: {name!r}") from None


def reject_outside(chars: Iterable[str]) -> None:
    """収録外の字が1つでもあれば ValueError。空は通す。"""
    outside = [ch for ch in chars if ch not in _BY_CHAR]
    if outside:
        shown = ", ".join(repr(ch) for ch in outside)
        raise ValueError(f"outside required latin set: {shown}")


def read_glyphset_file(path: Path) -> tuple[str, ...]:
    """1行1字の glyphset を読む。空・複数字・重複は ValueError。

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
        if len(line) != 1:
            raise ValueError(f"{path}: line {i} must be exactly 1 character, got {line!r}")
        if line in seen:
            raise ValueError(f"{path}: line {i} duplicates {line!r}")
        seen.add(line)
        chars.append(line)
    if not chars:
        raise ValueError(f"{path}: glyphset is empty")
    return tuple(chars)
