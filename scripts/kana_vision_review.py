#!/usr/bin/env python3
"""仮名レビューループ C: Gemini 観察（合否なし・任意レーン）。

GEMINI_API_KEY が無ければ status=skipped で終了（B の合否には影響しない）。
CI では走らせない。

例:
  python scripts/kana_vision_review.py --glyph shi
  python scripts/kana_vision_review.py --glyph shi --png proofs/out/kana/shi/single.png
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "scripts" / "prompts" / "kana_review_v1.txt"
DEFAULT_MODEL = "gemini-2.0-flash"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kana vision observation (optional C)")
    ap.add_argument("--glyph", required=True)
    ap.add_argument(
        "--png",
        type=Path,
        default=None,
        help="input PNG (default: proofs/out/kana/<glyph>/single.png)",
    )
    ap.add_argument("--iter", type=int, default=1, help="iteration index for out path")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "proofs" / "review",
    )
    args = ap.parse_args(argv)

    png = args.png or (ROOT / "proofs" / "out" / "kana" / args.glyph / "single.png")
    out_dir = args.out_root / args.glyph
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{args.iter}.json"

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        payload = {
            "status": "skipped",
            "reason": "GEMINI_API_KEY not set",
            "glyph_id": args.glyph,
            "png": str(png) if png.is_file() else None,
            "note": "C is optional; B gate decides pass/fail",
        }
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"status=skipped report={out_json}")
        return 0

    if not png.is_file():
        print(f"error: PNG not found: {png}", file=sys.stderr)
        return 2
    if not PROMPT_PATH.is_file():
        print(f"error: prompt missing: {PROMPT_PATH}", file=sys.stderr)
        return 2

    png_sha = _sha256_file(png)
    cache_path = out_dir / f"cache_{png_sha[:16]}.json"
    if cache_path.is_file():
        out_json.write_text(cache_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"status=cache_hit report={out_json}")
        return 0

    # 遅延 import（キー無し経路を軽く保つ）
    try:
        import urllib.error
        import urllib.request
    except ImportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # 対象文字
    char = args.glyph
    engine_src = ROOT / "engine" / "src"
    if str(engine_src) not in sys.path:
        sys.path.insert(0, str(engine_src))
    try:
        from engine.kana import KANA_GLYPH_META, kana_characters

        kana_characters()
        if args.glyph in KANA_GLYPH_META:
            char = str(KANA_GLYPH_META[args.glyph]["char"])
    except Exception:
        pass

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt += f"\n\n対象文字: {char}\n"
    import base64

    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{args.model}:generateContent?key={key}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"error: Gemini HTTP {e.code}: {err[:400]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"error: Gemini network: {e}", file=sys.stderr)
        return 1

    text = ""
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        observation = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        observation = {"raw_text": text, "parse_error": True}

    # 合否語が混入しても無視（status には載せない）
    payload = {
        "status": "ok",
        "glyph_id": args.glyph,
        "char": char,
        "model": args.model,
        "png": str(png),
        "png_sha256": png_sha,
        "prompt": str(PROMPT_PATH.name),
        "observation": observation,
        "note": "observation only; ignore any OK/NG if present",
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out_json.write_text(blob, encoding="utf-8")
    cache_path.write_text(blob, encoding="utf-8")
    print(f"status=ok report={out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
