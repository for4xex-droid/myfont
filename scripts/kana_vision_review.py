#!/usr/bin/env python3
"""仮名レビューループ C: Gemini 観察（合否なし・任意レーン）。

キーは環境変数 `GEMINI_API_KEY`、またはリポジトリ直下の `.env`（gitignore 済み）。
無い場合は status=skipped（B の合否には影響しない）。CI では走らせない。

例:
  cp .env.example .env   # 値を書き換えて chmod 600 .env
  python scripts/kana_vision_review.py --glyph shi
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from load_dotenv import load_repo_dotenv, redact_secrets  # noqa: E402

PROMPT_PATH = ROOT / "scripts" / "prompts" / "kana_review_v1.txt"
DEFAULT_MODEL = "gemini-2.0-flash"
PLACEHOLDER_KEYS = frozenset(
    {"", "your_gemini_api_key_here", "changeme", "xxx", "TODO"}
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_api_key() -> tuple[str | None, str]:
    """(key or None, source). source は env / dotenv / missing / placeholder。"""
    load_repo_dotenv(ROOT)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None, "missing"
    if key in PLACEHOLDER_KEYS:
        return None, "placeholder"
    # 既に export されていたか、dotenv 由来かは厳密に区別しない（値は出さない）
    source = "env_or_dotenv"
    return key, source


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

    key, key_source = _resolve_api_key()
    if not key:
        reason = (
            "GEMINI_API_KEY is placeholder; set a real key in .env"
            if key_source == "placeholder"
            else "GEMINI_API_KEY not set (export or repo-root .env)"
        )
        payload = {
            "status": "skipped",
            "reason": reason,
            "glyph_id": args.glyph,
            "png": str(png) if png.is_file() else None,
            "note": "C is optional; B gate decides pass/fail. See .env.example",
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

    import urllib.error
    import urllib.request

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
    # キーはクエリに載せない（ログ・プロキシ履歴への混入を減らす）
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{args.model}:generateContent"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(
            f"error: Gemini HTTP {e.code}: {redact_secrets(err[:400], key)}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as e:
        print(
            f"error: Gemini network: {redact_secrets(str(e), key)}",
            file=sys.stderr,
        )
        return 1

    text = ""
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        observation = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        observation = {"raw_text": text, "parse_error": True}

    # 合否語が混入しても無視。キーは絶対に書き出さない。
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
