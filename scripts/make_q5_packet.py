#!/usr/bin/env python3
"""P-Q5 内部再確認パック。P1黄金(before)と現行レンダ(after)を A/B する。

評価者には ui/hud の A.png B.png と SHEET だけ渡す。SEALED は渡さない。
α 本盲検（ui.txt/hud.txt）は欠字が埋まるまでやらない。黄金再凍結は合格後。

例:
  engine/.venv/bin/python scripts/compile_manual_otf.py
  engine/.venv/bin/python scripts/make_q5_packet.py
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OTF = ROOT / "fonts_out" / "build" / "MyMincho.otf"
DEFAULT_GOLDEN = ROOT / "proofs" / "golden" / "g3_blind"
DEFAULT_OUT = ROOT / "proofs" / "q5"
FACES = ("ui_kana", "hud_kana")
REVIEW_DIR = {"ui_kana": "ui", "hud_kana": "hud"}
AUTHOR_FACE = "walk_kana"


def pair_order(seed: int, face: str) -> dict[str, str]:
    rng = random.Random(f"{seed}:{face}")
    if rng.randrange(2) == 0:
        return {"A": "before", "B": "after"}
    return {"A": "after", "B": "before"}


def write_pair(before: Path, after: Path, dest: Path, order: dict[str, str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {"before": before, "after": after}
    (dest / "A.png").write_bytes(mapping[order["A"]].read_bytes())
    (dest / "B.png").write_bytes(mapping[order["B"]].read_bytes())


def build_packet(
    golden: Path, after_dir: Path, out: Path, *, seed: int
) -> dict:
    sealed: dict = {
        "seed": seed,
        "compare": "g3_blind_before_vs_current_after",
        "faces": {},
    }
    for face in FACES:
        before = golden / f"{face}.png"
        after = after_dir / f"{face}.png"
        if not before.is_file():
            raise FileNotFoundError(f"missing before {before}")
        if not after.is_file():
            raise FileNotFoundError(f"missing after {after}")
        order = pair_order(seed, face)
        write_pair(before, after, out / REVIEW_DIR[face], order)
        sealed["faces"][REVIEW_DIR[face]] = order
    out.mkdir(parents=True, exist_ok=True)
    (out / "SEALED_order.json").write_text(
        json.dumps(sealed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return sealed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build Q5 before/after A/B packet")
    ap.add_argument("--font", type=Path, default=DEFAULT_OTF)
    ap.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=20260817)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_proofs as mp

    if not args.font.is_file():
        print(f"error: missing OTF {args.font}", file=sys.stderr)
        return 2
    after_dir = args.out / "_after"
    after_dir.mkdir(parents=True, exist_ok=True)
    for face in (*FACES, AUTHOR_FACE):
        r = mp.render_face(args.font, face, after_dir)
        if not r.get("ok"):
            print(f"error: render failed {face}: {r}", file=sys.stderr)
            return 1
    try:
        sealed = build_packet(args.golden, after_dir, args.out, seed=args.seed)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    walk_src = after_dir / f"{AUTHOR_FACE}.png"
    if walk_src.is_file():
        (args.out / "walk_after.png").write_bytes(walk_src.read_bytes())
    print(json.dumps(sealed, ensure_ascii=False, indent=2))
    print(f"wrote {args.out / 'SEALED_order.json'}")
    print("pass only ui/ and hud/ plus SHEET.txt to the reviewer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
