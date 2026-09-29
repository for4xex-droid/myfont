#!/usr/bin/env python3
"""生成書体の仕様を読んで、未決定のままフォントファイルを出さない。

正本は docs/生成書体の仕様.md。このスクリプトは仕様を写さない。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "docs" / "生成書体の仕様.md"

# 収録節の箇条書きだけを字に展開する。未知の箇条は推測しない。
_BULLETS = {
    "大文字 A〜Z": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "数字 0〜9": list("0123456789"),
    "スラッシュ `/`": ["/"],
}

_BLOCKER_SECTIONS = (
    "ファイル形式",
    "太さの数",
    "等幅かどうか",
    "命名の規則",
)


class HandoffBlocked(RuntimeError):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("handoff blocked: " + ", ".join(reasons))


@dataclass(frozen=True)
class GeneratedFaceSpec:
    required: tuple[str, ...]
    blockers: tuple[str, ...]


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^### ", text, flags=re.M)
    out: dict[str, str] = {}
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        out[title.strip()] = body
    return out


def _required(body: str) -> tuple[str, ...]:
    chars: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip()
        if item not in _BULLETS:
            raise ValueError(f"unknown repertoire bullet: {item}")
        for ch in _BULLETS[item]:
            if ch not in chars:
                chars.append(ch)
    if not chars:
        raise ValueError("repertoire is empty")
    return tuple(chars)


def _blockers(sections: dict[str, str]) -> tuple[str, ...]:
    found: list[str] = []
    for title in _BLOCKER_SECTIONS:
        body = sections.get(title)
        if body is None:
            found.append(f"{title}: 節がない")
        elif "未決定" in body:
            found.append(title)
    return tuple(found)


def parse_spec(text: str) -> GeneratedFaceSpec:
    sections = _sections(text)
    if "収録する字の範囲" not in sections:
        raise ValueError("収録する字の範囲 is missing")
    return GeneratedFaceSpec(
        required=_required(sections["収録する字の範囲"]),
        blockers=_blockers(sections),
    )


def load_spec(path: Path | None = None) -> GeneratedFaceSpec:
    src = path or SPEC_PATH
    return parse_spec(src.read_text(encoding="utf-8"))


def reject_extras(spec: GeneratedFaceSpec, chars: list[str]) -> None:
    extra = [ch for ch in chars if ch not in spec.required]
    if extra:
        raise HandoffBlocked([f"収録外: {''.join(extra)}"])


def block_handoff(spec: GeneratedFaceSpec, dest: Path) -> tuple[str, ...]:
    """未決定が残るあいだは dest を作らない。中身の生成もしない。"""
    if spec.blockers:
        raise HandoffBlocked(list(spec.blockers))
    if dest.exists():
        raise HandoffBlocked(["既存ファイルは上書きしない"])
    return spec.required


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read the generated-face spec and refuse an early handoff")
    ap.add_argument("--spec", type=Path, default=SPEC_PATH)
    args = ap.parse_args(argv)
    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("required=" + "".join(spec.required))
    if spec.blockers:
        print("blocked=" + ",".join(spec.blockers), file=sys.stderr)
        return 2
    print("blocked=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
