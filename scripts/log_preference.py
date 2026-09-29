#!/usr/bin/env python3
"""keep / discard / shift の方針ログ。美の点数は付けない。

例:
  engine/.venv/bin/python scripts/log_preference.py \\
    --glyph つ --axis futokoro --left 0.06 --right 0.10 --choice keep_right
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "proofs" / "preference" / "log.jsonl"
SCHEMA = "mymincho.preference.v1"
CHOICES = ("keep_left", "keep_right", "discard", "shift")
BANNED = frozenset({"score", "fitness", "pretty", "beauty"})


def make_record(
    glyph: str,
    axis: str,
    left: float,
    right: float,
    choice: str,
    note: str = "",
    shift_to: float | None = None,
    ts: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    banned = BANNED.intersection(extra)
    if banned:
        raise ValueError(f"preference log is not a fitness: refuse {sorted(banned)}")
    if extra:
        raise TypeError(f"unknown fields: {sorted(extra)}")
    if choice not in CHOICES:
        raise ValueError(f"choice must be one of {CHOICES}, got {choice!r}")
    if len(glyph) != 1:
        raise ValueError(f"expected one char, got {glyph!r}")
    if not axis:
        raise ValueError("axis is required")
    if choice == "shift" and shift_to is None:
        raise ValueError("shift requires shift_to")
    if choice != "shift" and shift_to is not None:
        raise ValueError("shift_to is only for choice=shift")
    rec: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "glyph": glyph,
        "axis": axis,
        "left": float(left),
        "right": float(right),
        "choice": choice,
        "note": note,
        "not_fitness": True,
    }
    if shift_to is not None:
        rec["shift_to"] = float(shift_to)
    return rec


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("schema") != SCHEMA:
            raise ValueError(f"unknown schema: {rec.get('schema')}")
        if rec.get("not_fitness") is not True:
            raise ValueError("record missing not_fitness=true")
        if any(k in rec for k in BANNED):
            raise ValueError("fitness fields are forbidden")
        rows.append(rec)
    return rows


def policy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """選択回数だけ。平均点は出さない。"""
    counts = Counter(r["choice"] for r in rows)
    return {
        "n": len(rows),
        "counts": {k: counts.get(k, 0) for k in CHOICES},
        "axes": sorted({r["axis"] for r in rows}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append a keep/discard/shift preference (not a score)")
    ap.add_argument("--glyph", required=True)
    ap.add_argument("--axis", required=True)
    ap.add_argument("--left", type=float, required=True)
    ap.add_argument("--right", type=float, required=True)
    ap.add_argument("--choice", required=True, choices=CHOICES)
    ap.add_argument("--shift-to", type=float, default=None)
    ap.add_argument("--note", default="")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    try:
        rec = make_record(
            glyph=args.glyph,
            axis=args.axis,
            left=args.left,
            right=args.right,
            choice=args.choice,
            note=args.note,
            shift_to=args.shift_to,
        )
    except (TypeError, ValueError) as e:
        print(f"error: {e}", file=__import__("sys").stderr)
        return 2
    append_jsonl(args.out, rec)
    print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
