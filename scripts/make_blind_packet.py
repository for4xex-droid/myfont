#!/usr/bin/env python3
"""P1 仮名盲検パック。書体名は画像に出さず A/B だけ。対応表は SEALED に書く。

例:
  engine/.venv/bin/python scripts/make_blind_packet.py \\
    --font fonts_out/build/MyMincho.otf --seed 20260816
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OURS = ROOT / "fonts_out" / "build" / "MyMincho.otf"
DEFAULT_COMPARE = ROOT / "fontdb" / "data" / "fonts" / "ipaex_mincho-Regular.ttf"
DEFAULT_OUT = ROOT / "proofs" / "out" / "blind"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build A/B blind packet without font names")
    ap.add_argument("--font", type=Path, default=DEFAULT_OURS)
    ap.add_argument("--compare", type=Path, default=DEFAULT_COMPARE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--faces", default="ui_kana,hud_kana")
    ap.add_argument("--seed", type=int, default=20260816)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_proofs as mp

    faces = [f.strip() for f in args.faces.split(",") if f.strip()]
    for face in faces:
        if face not in mp.FACE_ORDER:
            print(f"error: unknown face {face!r}", file=sys.stderr)
            return 2
    if not args.font.is_file():
        print(f"error: missing ours {args.font}", file=sys.stderr)
        return 2
    if not args.compare.is_file():
        print(f"error: missing compare {args.compare}", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    sealed: dict = {"seed": args.seed, "compare_key": "compare_a", "faces": {}}
    failed = False
    for face in faces:
        ours_dir = args.out / face / "_ours"
        cmp_dir = args.out / face / "_compare"
        ours_dir.mkdir(parents=True, exist_ok=True)
        cmp_dir.mkdir(parents=True, exist_ok=True)
        r_ours = mp.render_face(args.font, face, ours_dir)
        r_cmp = mp.render_face(args.compare, face, cmp_dir)
        if not (r_ours.get("ok") and r_cmp.get("ok")):
            print(f"error: render failed {face}", file=sys.stderr)
            failed = True
            continue
        ours_png = Path(r_ours["png"])
        cmp_png = Path(r_cmp["png"])
        pair = args.out / face
        if rng.randrange(2) == 0:
            order = {"A": "ours", "B": "compare_a"}
            (pair / "A.png").write_bytes(ours_png.read_bytes())
            (pair / "B.png").write_bytes(cmp_png.read_bytes())
        else:
            order = {"A": "compare_a", "B": "ours"}
            (pair / "A.png").write_bytes(cmp_png.read_bytes())
            (pair / "B.png").write_bytes(ours_png.read_bytes())
        sealed["faces"][face] = order
        print(f"ok {face} A/B written (order sealed)")

    seal_path = args.out / "SEALED_order.json"
    seal_path.write_text(
        json.dumps(sealed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"sealed={seal_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
