#!/usr/bin/env python3
"""KAGE 語彙カタログ。座標は返さない。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "kage_vocab.yaml"


def load_vocab(path: Path = VOCAB_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "mymincho.kage_vocab.v1":
        raise ValueError(f"unknown schema: {raw.get('schema')}")
    if raw.get("coordinates") is not False:
        raise ValueError("kage vocab must not carry coordinates")
    for key in ("outline", "contour", "points"):
        if key in raw:
            raise ValueError(f"forbidden key {key}")
    return raw


def map_end_tag(tag: int, which: str) -> str:
    vocab = load_vocab()
    table = vocab["start_tags"] if which == "start" else vocab["end_tags"]
    return str(table.get(str(int(tag)), "none"))


if __name__ == "__main__":
    v = load_vocab()
    print(f"{v['schema']} coordinates={v['coordinates']} kinds={len(v['engine_kinds'])}")
